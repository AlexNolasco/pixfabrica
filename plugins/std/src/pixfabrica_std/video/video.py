from __future__ import annotations

import asyncio
import logging
import os
from collections import OrderedDict
from contextlib import suppress
from pathlib import Path
from typing import Any, ClassVar

import av
import numpy as np
import skia
from av.error import EOFError as AvEOFError
from pydantic import Field, PrivateAttr

from pixfabrica_core.clips import ClipCategory, ClipSkia, ClipTag, PrepareContext, RenderContext
from pixfabrica_core.graphics import Rect
from pixfabrica_core.prepare_diagnostics import record_prepare_asset_failure
from pixfabrica_core.ui_schema import (
    stock_attribution_field,
    stock_provider_field,
    stock_video_field,
)
from pixfabrica_std.common import FitMode

log = logging.getLogger("pixfabrica.std.video")

# LRU decoded frames (Skia images). Bounded memory vs full pre-decode.
_CACHE_SIZE = max(4, min(128, int(os.environ.get("PIXFABRICA_VIDEO_CACHE_FRAMES", "24"))))


class Video(ClipSkia):
    """Plays a video file within its bounds.

    ``prepare()`` opens the container and reads stream metadata only. Frames are
    decoded on demand in ``draw()`` with a small LRU cache (``PIXFABRICA_VIDEO_CACHE_FRAMES``,
    default 24). For multi-process renders, prefer ``parallelism=single`` when this
    clip is used (UI policy) — each worker would otherwise hold its own decoder.
    """

    clip_type: ClassVar[str] = "std-video"
    clip_category: ClassVar[ClipCategory] = ClipCategory.VIDEO
    clip_tags: ClassVar[list[str]] = [ClipTag.VIDEO]

    source: str = stock_video_field(default="", description="Absolute path to the video file")
    loop: bool = Field(
        default=False, description="Loop playback when source is shorter than clip duration"
    )
    fit: FitMode = Field(default=FitMode.COVER, description="How the video frame fills the bounds")
    start_offset: float = Field(
        default=0.0, ge=0.0, description="Seconds into the source to begin playback"
    )
    volume: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Stored for future audio bus extraction",
    )
    playback_rate: float = Field(
        default=1.0,
        ge=0.0,
        le=5.0,
        multiple_of=0.1,
        description="Playback speed multiplier (1.0 = normal speed)",
    )
    flip_h: bool = Field(default=False, description="Flip frame horizontally")
    flip_v: bool = Field(default=False, description="Flip frame vertically")
    source_attribution: str = stock_attribution_field("source")
    source_provider: str = stock_provider_field("source")

    # ── Private state ────────────────────────────────────────────────────────
    _container: Any = PrivateAttr(default=None)
    _stream: Any = PrivateAttr(default=None)
    _src_fps: float = PrivateAttr(default=30.0)
    _src_duration: float = PrivateAttr(default=0.0)  # seconds
    _src_width: int = PrivateAttr(default=0)
    _src_height: int = PrivateAttr(default=0)
    _total_src_frames: int = PrivateAttr(default=0)

    _cache: OrderedDict[int, skia.Image] = PrivateAttr(default_factory=OrderedDict)
    _cache_size: int = PrivateAttr(default=_CACHE_SIZE)

    _last_decoded_index: int = PrivateAttr(default=-1)
    _last_good_image: skia.Image | None = PrivateAttr(default=None)

    async def prepare(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        if not self.source:
            return
        await asyncio.to_thread(self._prepare_sync, ctx, bounds)

    def _prepare_sync(self, ctx: PrepareContext, _bounds: Rect | None = None) -> None:
        p = Path(self.source)
        if not p.is_file():
            exc = FileNotFoundError(f"Video file not found: {self.source}")
            record_prepare_asset_failure(
                ctx,
                kind="clip",
                ref_id=self.id,
                clip_type=self.clip_type,
                field="source",
                source=self.source,
                exc=exc,
            )
            log.warning("Video %s: %s", self.id, exc)
            return

        self._close_decoder()
        self._cache_size = _CACHE_SIZE

        try:
            container = av.open(str(p))
        except Exception as exc:
            record_prepare_asset_failure(
                ctx,
                kind="clip",
                ref_id=self.id,
                clip_type=self.clip_type,
                field="source",
                source=self.source,
                exc=exc,
            )
            log.warning("Video %s: failed to open %r — %s", self.id, self.source, exc)
            return

        self._container = container
        stream: av.VideoStream = container.streams.video[0]
        self._stream = stream
        if os.environ.get("PIXFABRICA_RENDERER_MP_WORKER") == "1":
            try:
                stream.thread_type = "NONE"
            except (AttributeError, TypeError, ValueError, OSError):
                stream.thread_type = "AUTO"
        else:
            stream.thread_type = "AUTO"

        codec_ctx = stream.codec_context
        self._src_width = codec_ctx.width
        self._src_height = codec_ctx.height

        if stream.average_rate:
            self._src_fps = float(stream.average_rate)
        elif stream.base_rate:
            self._src_fps = float(stream.base_rate)

        if stream.duration and stream.time_base:
            self._src_duration = float(stream.duration * stream.time_base)
        elif container.duration:
            self._src_duration = container.duration / av.time_base

        self._total_src_frames = max(1, int(self._src_duration * self._src_fps))

        log.debug(
            "video prepared: %s — %dx%d @ %.1f fps, %.1fs (%d frames), cache=%d",
            p.name,
            self._src_width,
            self._src_height,
            self._src_fps,
            self._src_duration,
            self._total_src_frames,
            self._cache_size,
        )

    def _close_decoder(self) -> None:
        if self._container is not None:
            with suppress(Exception):
                self._container.close()
            self._container = None
            self._stream = None
        self._cache.clear()
        self._last_decoded_index = -1
        self._last_good_image = None

    def draw(self, ctx: RenderContext) -> None:
        if self._container is None or self._stream is None:
            return

        local_t = ctx.time.t - self.start
        if local_t < 0:
            return

        src_time = (local_t * self.playback_rate) + self.start_offset

        if self.loop and self._src_duration > 0:
            src_time = src_time % self._src_duration

        if not self.loop:
            src_time = max(0.0, min(src_time, self._src_duration - 1e-6))

        frame_index = int(src_time * self._src_fps)
        frame_index = min(frame_index, self._total_src_frames - 1)

        image = self._get_frame(frame_index)
        if image is None:
            return

        self._draw_fitted(ctx.canvas, ctx.bounds, image)

    def _get_frame(self, index: int) -> skia.Image | None:
        if index in self._cache:
            self._cache.move_to_end(index)
            return self._cache[index]

        image = self._decode_frame(index)
        if image is not None:
            return image

        if self._cache:
            nearest = min(self._cache, key=lambda k: abs(k - index))
            return self._cache[nearest]
        return self._last_good_image

    def _cache_image(self, index: int, image: skia.Image) -> None:
        self._cache[index] = image
        self._last_good_image = image
        if len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)

    def _decode_frame(self, target_index: int) -> skia.Image | None:
        assert self._container is not None and self._stream is not None

        if (
            target_index < self._last_decoded_index
            or target_index > self._last_decoded_index + self._cache_size
        ):
            tb = self._stream.time_base
            pts = int(target_index / self._src_fps / float(tb)) if tb else target_index
            self._container.seek(pts, stream=self._stream)
            self._stream.codec_context.flush_buffers()
            self._last_decoded_index = max(0, target_index - 2)

        try:
            for packet in self._container.demux(self._stream):
                try:
                    for frame in packet.decode():
                        current_index = self._frame_index_from_pts(frame)
                        self._last_decoded_index = current_index

                        arr = frame.to_ndarray(format="rgba")
                        if not arr.flags.c_contiguous:
                            arr = np.ascontiguousarray(arr)
                        image = skia.Image.fromarray(
                            arr, colorType=skia.ColorType.kRGBA_8888_ColorType
                        )
                        self._cache_image(current_index, image)

                        if current_index >= target_index:
                            return image
                except AvEOFError:
                    continue
        except AvEOFError:
            pass
        return None

    def _frame_index_from_pts(self, frame: Any) -> int:
        if frame.pts is not None and self._stream is not None and self._stream.time_base:
            t = float(frame.pts * self._stream.time_base)
            return int(t * self._src_fps)
        return self._last_decoded_index + 1

    def _draw_fitted(self, canvas: skia.Canvas, bounds: Rect, image: skia.Image) -> None:
        src_w, src_h = image.width(), image.height()
        dst_w, dst_h = bounds.width, bounds.height

        if src_w == 0 or src_h == 0:
            return

        src_aspect = src_w / src_h
        dst_aspect = dst_w / dst_h

        match self.fit:
            case FitMode.CONTAIN:
                scale = dst_w / src_w if src_aspect > dst_aspect else dst_h / src_h
                draw_w = src_w * scale
                draw_h = src_h * scale
                dx = bounds.x + (dst_w - draw_w) / 2
                dy = bounds.y + (dst_h - draw_h) / 2

            case FitMode.COVER:
                scale = dst_h / src_h if src_aspect > dst_aspect else dst_w / src_w
                draw_w = src_w * scale
                draw_h = src_h * scale
                dx = bounds.x + (dst_w - draw_w) / 2
                dy = bounds.y + (dst_h - draw_h) / 2

            case FitMode.FIT_WIDTH:
                scale = dst_w / src_w
                draw_w = dst_w
                draw_h = src_h * scale
                dx = bounds.x
                dy = bounds.y + (dst_h - draw_h) / 2

            case FitMode.FIT_HEIGHT:
                scale = dst_h / src_h
                draw_w = src_w * scale
                draw_h = dst_h
                dx = bounds.x + (dst_w - draw_w) / 2
                dy = bounds.y

            case FitMode.STRETCH:
                draw_w = dst_w
                draw_h = dst_h
                dx = bounds.x
                dy = bounds.y

            case _:
                draw_w = dst_w
                draw_h = dst_h
                dx = bounds.x
                dy = bounds.y

        canvas.save()
        canvas.clipRect(skia.Rect.MakeXYWH(bounds.x, bounds.y, dst_w, dst_h))

        if self.flip_h or self.flip_v:
            cx = bounds.x + dst_w / 2
            cy = bounds.y + dst_h / 2
            canvas.translate(cx, cy)
            canvas.scale(-1.0 if self.flip_h else 1.0, -1.0 if self.flip_v else 1.0)
            canvas.translate(-cx, -cy)

        dst_rect = skia.Rect.MakeXYWH(dx, dy, draw_w, draw_h)
        src_rect = skia.Rect.MakeWH(src_w, src_h)
        canvas.drawImageRect(image, src_rect, dst_rect)

        canvas.restore()

    def close_av_container(self) -> None:
        """Release PyAV file handles and cached frames (worker processes call this)."""
        self._close_decoder()

    def __del__(self) -> None:
        if self._container is not None:
            with suppress(Exception):
                self._container.close()
