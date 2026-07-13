from __future__ import annotations

import logging
import math
from typing import ClassVar, Literal

import numpy as np
import skia
from PIL import Image as PILImage
from pydantic import Field, PrivateAttr

from pixfabrica_core.audio.mixin import AudioVisualMixin
from pixfabrica_core.clips import ClipCategory, ClipSkia, ClipTag, PrepareContext, RenderContext
from pixfabrica_core.file_upload_policy import JobBoundsFactorPolicy, manifest_covers_max_px
from pixfabrica_core.graphics import Rect
from pixfabrica_core.prepare_diagnostics import record_prepare_asset_failure
from pixfabrica_core.ui_schema import (
    stock_attribution_field,
    stock_image_field,
    stock_provider_field,
)
from pixfabrica_std.common import FitMode
from pixfabrica_std.media_source import resolve_local_source_path
from pixfabrica_std.mesh.shader_helper import precompute_bus_drives
from pixfabrica_std.tilt import ANGLE_FULL_DESC, ANGLE_FULL_MAX, ANGLE_FULL_MIN

log = logging.getLogger("pixfabrica.std.BackgroundImage")

# Cap long edge at factor × max(job width, job height). Upload (API) and prepare
# (CLI safety net) both use this via source_upload_policy().
#
# Example: 1280×1920 project → cap 2880 px long edge (factor 1.5) → 4160×6240 becomes 1920×2880.
# For smaller proxies (less disk/RAM, slightly softer at export): lower the factor —
# e.g. 1.5 → cap 2880 on that project; 1.0 → cap 1920 (1× job long edge, no headroom
# for bass scale or cover crop). Re-upload or re-ingest after changing; existing files
# in media/ are not re-optimized automatically.
_MAX_DIM_FACTOR = 1.5

MotionMode = Literal["none", "circular", "infinity", "bus_drift"]

# Baked pan radius as a fraction of min(bounds width, height).
_MOTION_AMOUNT_RATIO = 0.04
# Extra cover scale when motion is active so panning does not reveal clip edges.
_COVER_BOOST = 1.09
_TWO_PI = 2.0 * math.pi


class BackgroundImage(AudioVisualMixin, ClipSkia):
    """Image background with optional bass-reactive zoom or looping pan motion.

    When ``motion`` is ``none`` (default), an optional bus drives bass-reactive scale
    via ``sensitivity``. Motion presets disable zoom and instead translate the image.
    """

    clip_type: ClassVar[str] = "std-background-image"
    clip_category: ClassVar[ClipCategory] = ClipCategory.IMAGE
    clip_tags: ClassVar[list[str]] = [
        ClipTag.AUDIO_REACTIVE,
        ClipTag.ANIMATED,
        ClipTag.LOOP,
    ]

    source: str | None = stock_image_field(
        default=None,
        description="Local file path to a prepared image",
    )
    fit: FitMode = Field(default=FitMode.COVER, description="How the image fills the bounds")
    cover_scale: float = Field(
        default=1.0,
        ge=0.0,
        le=1.25,
        multiple_of=0.01,
        description=(
            "Extra scale when fit is cover (1 = tight crop). "
            "Track motion effects add render padding automatically; raise for more headroom."
        ),
    )
    angle: float = Field(
        default=0.0,
        ge=ANGLE_FULL_MIN,
        le=ANGLE_FULL_MAX,
        multiple_of=1.0,
        description=ANGLE_FULL_DESC,
    )
    opacity: float = Field(
        default=1.0, ge=0.0, le=1.0, multiple_of=0.1, description="Overall layer opacity"
    )
    motion: MotionMode = Field(
        default="none",
        description="Looping pan preset; none keeps the image static aside from optional zoom",
    )
    motion_speed: float = Field(
        default=20.0,
        ge=6.0,
        le=40.0,
        multiple_of=1.0,
        description="Seconds per full loop for circular, infinity, and bus drift fallback",
    )
    sensitivity: float = Field(
        default=0.15,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Max additive scale at full bass when motion is none (0 = no reactivity)",
    )
    source_attribution: str = stock_attribution_field("source")
    source_provider: str = stock_provider_field("source")

    _image: skia.Image | None = PrivateAttr(default=None)
    _smoothed_bass: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype=np.float32))
    _smoothed_mid: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype=np.float32))
    _bus_drift_active: bool = PrivateAttr(default=False)

    @classmethod
    def source_upload_policy(cls) -> JobBoundsFactorPolicy:
        return JobBoundsFactorPolicy(factor=_MAX_DIM_FACTOR)

    @classmethod
    def source_max_px(cls, bounds: Rect) -> int:
        return cls.source_upload_policy().max_px_from_bounds(bounds.width, bounds.height)

    async def prepare(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        import asyncio

        await asyncio.to_thread(self._prepare_sync, ctx, bounds)

    def _prepare_sync(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        total = max(ctx.job.total_frames, 0)
        bus = self.bus_timeline(ctx)
        self._smoothed_bass, self._smoothed_mid, _, _ = precompute_bus_drives(bus, total)
        self._bus_drift_active = bool(bus)

        if not self.source:
            return
        try:
            local_path = resolve_local_source_path(self.source)
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
            log.warning(
                "BackgroundImage %s: could not resolve source %r — %s", self.id, self.source, exc
            )
            return

        if not local_path.is_file():
            record_prepare_asset_failure(
                ctx,
                kind="clip",
                ref_id=self.id,
                clip_type=self.clip_type,
                field="source",
                source=self.source,
                exc=FileNotFoundError(local_path),
                code="not_found",
            )
            log.warning("BackgroundImage %s: source file not found %r", self.id, local_path)
            return

        try:
            pil_img = PILImage.open(str(local_path)).convert("RGBA")
        except Exception as exc:
            record_prepare_asset_failure(
                ctx,
                kind="clip",
                ref_id=self.id,
                clip_type=self.clip_type,
                field="source",
                source=self.source,
                exc=exc,
                code="load_failed",
            )
            log.warning(
                "BackgroundImage %s: failed to load image %r — %s", self.id, local_path, exc
            )
            return

        b = bounds or Rect(0, 0, ctx.job.width, ctx.job.height)
        max_dim = self.source_max_px(b)

        if (
            not manifest_covers_max_px(local_path, max_dim)
            and max(pil_img.width, pil_img.height) > max_dim
        ):
            pil_img.thumbnail((max_dim, max_dim), PILImage.Resampling.LANCZOS)
            log.debug(
                "BackgroundImage %s: downsampled to %dx%d", self.id, pil_img.width, pil_img.height
            )

        self._image = skia.Image.fromarray(
            np.array(pil_img),
            colorType=skia.ColorType.kRGBA_8888_ColorType,
        )

    def _bass_drive_for_frame(self, ctx: RenderContext) -> float:
        if not self.bus_active_for_draw(ctx):
            return 0.0
        if self._smoothed_bass.shape[0] > 0:
            f = max(0, min(ctx.time.frame, self._smoothed_bass.shape[0] - 1))
            return min(1.0, float(self._smoothed_bass[f]))
        return min(1.0, max(0.0, float(ctx.audio_bus_frame.bass)))

    def _local_t(self, ctx: RenderContext) -> float:
        return max(0.0, ctx.time.t - self.start)

    def _motion_amount_px(self, bounds: Rect) -> float:
        return _MOTION_AMOUNT_RATIO * float(min(bounds.width, bounds.height))

    def _motion_offset(self, ctx: RenderContext, bounds: Rect) -> tuple[float, float]:
        if self.motion == "none":
            return 0.0, 0.0

        amount = self._motion_amount_px(bounds)
        local_t = self._local_t(ctx)
        period = max(float(self.motion_speed), 1e-6)

        if self.motion == "bus_drift" and self._bus_drift_active:
            idx = max(0, min(ctx.time.frame, self._smoothed_bass.shape[0] - 1))
            if self._smoothed_bass.size:
                bass = float(self._smoothed_bass[idx])
                mid = float(self._smoothed_mid[idx])
                return (bass - 0.5) * 2.0 * amount, (mid - 0.5) * 2.0 * amount
            return 0.0, 0.0

        phase = _TWO_PI * (local_t / period)
        if self.motion == "infinity":
            sn = math.sin(phase)
            return amount * sn, amount * sn * math.cos(phase)

        # circular and bus_drift fallback (no bus timeline)
        return amount * math.cos(phase), amount * math.sin(phase)

    def draw(self, ctx: RenderContext) -> None:
        if self._image is None:
            return

        # Bus bass drives zoom only when motion is none; sensitivity is max additive scale.
        scale = (
            1.0 + self.sensitivity * self._bass_drive_for_frame(ctx)
            if self.motion == "none"
            else 1.0
        )

        canvas: skia.Canvas = ctx.canvas
        bnd = ctx.bounds
        dx, dy = self._motion_offset(ctx, bnd)
        pad = max(0.0, float(ctx.overscan))
        cover_boost = self.cover_scale
        if self.motion != "none":
            cover_boost *= _COVER_BOOST

        draw_bnd = bnd
        if pad > 0.0:
            mx = bnd.width * pad
            my = bnd.height * pad
            draw_bnd = Rect(bnd.x - mx, bnd.y - my, bnd.width + 2.0 * mx, bnd.height + 2.0 * my)

        paint = skia.Paint()
        paint.setAlphaf(self.opacity)

        canvas.save()
        bleed = pad > 0.0 or cover_boost > 1.0
        if not bleed:
            # Constrain to clip bounds before transforms so motion/zoom stay contained.
            canvas.clipRect(skia.Rect.MakeXYWH(bnd.x, bnd.y, float(bnd.width), float(bnd.height)))

        cx = bnd.x + bnd.width / 2.0
        cy = bnd.y + bnd.height / 2.0
        canvas.translate(cx + dx, cy + dy)
        canvas.rotate(self.angle)
        canvas.scale(scale, scale)
        canvas.translate(-cx, -cy)

        _draw_fitted(canvas, draw_bnd, self._image, self.fit, paint, cover_boost=cover_boost)
        canvas.restore()


def _draw_fitted(
    canvas: skia.Canvas,
    bounds: Rect,
    image: skia.Image,
    fit: FitMode,
    paint: skia.Paint,
    *,
    cover_boost: float = 1.0,
) -> None:
    src_w, src_h = float(image.width()), float(image.height())
    dst_w, dst_h = float(bounds.width), float(bounds.height)

    if src_w == 0 or src_h == 0:
        return

    src_aspect = src_w / src_h
    dst_aspect = dst_w / dst_h

    match fit:
        case FitMode.CONTAIN:
            s = dst_w / src_w if src_aspect > dst_aspect else dst_h / src_h
            draw_w, draw_h = src_w * s, src_h * s
            dx = bounds.x + (dst_w - draw_w) / 2
            dy = bounds.y + (dst_h - draw_h) / 2
        case FitMode.COVER:
            s = dst_h / src_h if src_aspect > dst_aspect else dst_w / src_w
            s *= cover_boost
            draw_w, draw_h = src_w * s, src_h * s
            dx = bounds.x + (dst_w - draw_w) / 2
            dy = bounds.y + (dst_h - draw_h) / 2
        case FitMode.FIT_WIDTH:
            s = dst_w / src_w
            draw_w, draw_h = dst_w, src_h * s
            dx, dy = float(bounds.x), bounds.y + (dst_h - draw_h) / 2
        case FitMode.FIT_HEIGHT:
            s = dst_h / src_h
            draw_w, draw_h = src_w * s, dst_h
            dx, dy = bounds.x + (dst_w - draw_w) / 2, float(bounds.y)
        case _:  # STRETCH
            draw_w, draw_h = dst_w, dst_h
            dx, dy = float(bounds.x), float(bounds.y)

    canvas.drawImageRect(
        image,
        skia.Rect.MakeWH(src_w, src_h),
        skia.Rect.MakeXYWH(dx, dy, draw_w, draw_h),
        skia.SamplingOptions(skia.FilterMode.kLinear),
        paint,
    )
