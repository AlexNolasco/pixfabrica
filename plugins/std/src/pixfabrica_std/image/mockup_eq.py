from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar, cast

import numpy as np
import skia
from PIL import Image as PILImage
from pydantic import Field, PrivateAttr, field_validator
from scipy import ndimage

from pixfabrica_core.audio.bus import N_SPECTRUM, AudioBusFrame
from pixfabrica_core.audio.mixin import AudioVisualMixin
from pixfabrica_core.clips import ClipCategory, ClipSkia, ClipTag, PrepareContext, RenderContext
from pixfabrica_core.file_upload_policy import JobBoundsFactorPolicy, manifest_covers_max_px
from pixfabrica_core.graphics import Rect
from pixfabrica_core.prepare_diagnostics import record_prepare_asset_failure
from pixfabrica_core.theme.color import Color, ColorToken, color_field, resolve_color
from pixfabrica_std.media_source import resolve_local_source_path

log = logging.getLogger("pixfabrica.std.MockupEq")

_MAX_DIM_FACTOR = 1.5
_KEY_TOLERANCE = 12
_SLOT_KEY_TOLERANCE = 0
_KEY_MASK_DILATE = 2
_KEY_BBOX_PAD = 3
_MIN_BLOB_FRAC = 0.03
_BAR_GAP_RATIO = 0.12
_BUS_EMA_SMOOTHING = 0.85
_MAX_BARS = 24
_MIN_SEGMENT_PX = 3.5
_SEGMENT_GAP_RATIO = 0.25
_DEFAULT_KEY = Color("#00FF00")


class SlotBackgroundMode(StrEnum):
    TRANSPARENT = "transparent"
    CUSTOM = "custom"


@dataclass(frozen=True, slots=True)
class _CoverFit:
    scale: float
    dx: float
    dy: float
    draw_w: float
    draw_h: float


@dataclass(frozen=True, slots=True)
class _ImageBlob:
    x: int
    y: int
    width: int
    height: int
    area: int


def _cover_fit(src_w: float, src_h: float, bounds: Rect) -> _CoverFit:
    dst_w, dst_h = float(bounds.width), float(bounds.height)
    src_aspect = src_w / src_h
    dst_aspect = dst_w / dst_h
    scale = dst_h / src_h if src_aspect > dst_aspect else dst_w / src_w
    draw_w = src_w * scale
    draw_h = src_h * scale
    dx = bounds.x + (dst_w - draw_w) / 2.0
    dy = bounds.y + (dst_h - draw_h) / 2.0
    return _CoverFit(scale=scale, dx=dx, dy=dy, draw_w=draw_w, draw_h=draw_h)


def _key_rgb(key: Color) -> tuple[int, int, int]:
    r, g, b, _ = key.rgba
    return int(round(r * 255.0)), int(round(g * 255.0)), int(round(b * 255.0))


def _color_match_mask(rgba: np.ndarray, key: Color, tolerance: int) -> np.ndarray:
    target = np.array(_key_rgb(key), dtype=np.int16)
    diff = np.abs(rgba[..., :3].astype(np.int16) - target).max(axis=-1)
    return diff <= tolerance


def _find_blobs(mask: np.ndarray, *, min_w: int, min_h: int) -> list[_ImageBlob]:
    labeled = np.zeros(mask.shape, dtype=np.int32)
    count = cast(int, ndimage.label(mask, output=labeled))
    blobs: list[_ImageBlob] = []
    for label_id in range(1, count + 1):
        ys, xs = np.nonzero(labeled == label_id)
        if ys.size == 0:
            continue
        x0 = int(xs.min())
        y0 = int(ys.min())
        x1 = int(xs.max()) + 1
        y1 = int(ys.max()) + 1
        w = x1 - x0
        h = y1 - y0
        if w < min_w or h < min_h:
            continue
        blobs.append(_ImageBlob(x=x0, y=y0, width=w, height=h, area=w * h))
    blobs.sort(key=lambda blob: blob.area, reverse=True)
    return blobs


def _map_blob_to_bounds(blob: _ImageBlob, cover: _CoverFit) -> Rect:
    return Rect(
        cover.dx + blob.x * cover.scale,
        cover.dy + blob.y * cover.scale,
        blob.width * cover.scale,
        blob.height * cover.scale,
    )


def _contract_blob(blob: _ImageBlob, pad: int, *, img_w: int, img_h: int) -> _ImageBlob:
    """Inset a blob rectangle — approximates strict slot bounds inside a dilated mask."""
    if pad <= 0:
        return blob
    x0 = min(blob.x + pad, blob.x + blob.width)
    y0 = min(blob.y + pad, blob.y + blob.height)
    x1 = max(x0, blob.x + blob.width - pad)
    y1 = max(y0, blob.y + blob.height - pad)
    w = max(x1 - x0, 0)
    h = max(y1 - y0, 0)
    if w <= 0 or h <= 0:
        return blob
    return _ImageBlob(x=x0, y=y0, width=w, height=h, area=w * h)


def _resolve_slot_blobs(
    rgba: np.ndarray,
    key: Color,
    *,
    min_w: int,
    min_h: int,
    dilated_blobs: list[_ImageBlob],
) -> list[_ImageBlob]:
    """Pick slot geometry: exact key fill first, then tolerant match, then inset dilated blob."""
    img_h, img_w = rgba.shape[:2]

    strict_mask = _color_match_mask(rgba, key, _SLOT_KEY_TOLERANCE)
    if strict_mask.any():
        closed = ndimage.binary_closing(strict_mask, iterations=1)
        blobs = _find_blobs(closed, min_w=min_w, min_h=min_h)
        if blobs:
            return blobs

    soft_mask = _color_match_mask(rgba, key, _KEY_TOLERANCE)
    blobs = _find_blobs(soft_mask, min_w=min_w, min_h=min_h)
    if blobs:
        return blobs

    if dilated_blobs:
        inset = _KEY_MASK_DILATE + _KEY_BBOX_PAD
        return [_contract_blob(blob, inset, img_w=img_w, img_h=img_h) for blob in dilated_blobs]
    return []


def _pad_slot_rect(slot: Rect, pad: float) -> Rect:
    if pad <= 0.0:
        return slot
    return Rect(slot.x - pad, slot.y - pad, slot.width + 2.0 * pad, slot.height + 2.0 * pad)


def _apply_key_out(rgba: np.ndarray, mask: np.ndarray) -> np.ndarray:
    out = rgba.copy()
    out[mask, 3] = 0
    out[mask, :3] = 0
    return out


def _expand_blob(blob: _ImageBlob, pad: int, *, img_w: int, img_h: int) -> _ImageBlob:
    x0 = max(0, blob.x - pad)
    y0 = max(0, blob.y - pad)
    x1 = min(img_w, blob.x + blob.width + pad)
    y1 = min(img_h, blob.y + blob.height + pad)
    w = max(x1 - x0, 0)
    h = max(y1 - y0, 0)
    return _ImageBlob(x=x0, y=y0, width=w, height=h, area=w * h)


def _key_out_blob_rect(rgba: np.ndarray, blob: _ImageBlob) -> None:
    """Clear the slot box — catches JPEG fringe and anti-aliased slot edges."""
    y0 = max(blob.y, 0)
    x0 = max(blob.x, 0)
    y1 = min(blob.y + blob.height, rgba.shape[0])
    x1 = min(blob.x + blob.width, rgba.shape[1])
    if y1 <= y0 or x1 <= x0:
        return
    rgba[y0:y1, x0:x1, 3] = 0
    rgba[y0:y1, x0:x1, :3] = 0


def _finalize_keyed_rgba(
    rgba: np.ndarray, mask: np.ndarray, primary: _ImageBlob | None
) -> np.ndarray:
    keyed = _apply_key_out(rgba, mask)
    if primary is not None:
        padded = _expand_blob(primary, _KEY_BBOX_PAD, img_w=rgba.shape[1], img_h=rgba.shape[0])
        _key_out_blob_rect(keyed, padded)
    transparent = keyed[..., 3] == 0
    keyed[transparent, :3] = 0
    return keyed


def _normalize_bar_timeline(raw: np.ndarray) -> np.ndarray:
    """Stretch each bar column to ~0..1 using robust job-wide percentiles."""
    if raw.size == 0:
        return raw
    out = np.empty_like(raw)
    for col in range(raw.shape[1]):
        channel = raw[:, col]
        lo, hi = np.percentile(channel, (5.0, 95.0))
        span = max(float(hi - lo), 1e-6)
        out[:, col] = np.clip((channel - lo) / span, 0.0, 1.0)
    return out


def _bar_bin_slices(bar_count: int) -> list[tuple[int, int]]:
    edges = np.linspace(0, N_SPECTRUM, bar_count + 1, dtype=int)
    return [(int(edges[i]), int(edges[i + 1])) for i in range(bar_count)]


def _freq_to_bars(freq: np.ndarray, slices: list[tuple[int, int]]) -> np.ndarray:
    out = np.empty(len(slices), dtype=np.float32)
    for i, (lo, hi) in enumerate(slices):
        chunk = freq[lo : max(hi, lo + 1)]
        out[i] = float(chunk.mean()) if chunk.size else 0.0
    return out


def _bars_from_coarse_bands(bass: float, mid: float, high: float, bar_count: int) -> np.ndarray:
    """Spread bass/mid/high across bar columns when spectrum is empty but bands have energy."""
    if bar_count <= 0:
        return np.zeros(0, dtype=np.float32)
    if bar_count == 1:
        return np.array([mid], dtype=np.float32)
    xs = np.linspace(0.0, 1.0, bar_count, dtype=np.float32)
    anchors_x = np.array([0.0, 0.5, 1.0], dtype=np.float32)
    anchors_y = np.array([bass, mid, high], dtype=np.float32)
    return np.interp(xs, anchors_x, anchors_y).astype(np.float32)


def _frame_to_bars(
    freq: np.ndarray,
    slices: list[tuple[int, int]],
    *,
    bass: float,
    mid: float,
    high: float,
) -> np.ndarray:
    if float(freq.max()) < 1e-6 and max(bass, mid, high) > 1e-6:
        return _bars_from_coarse_bands(bass, mid, high, len(slices))
    return _freq_to_bars(freq, slices)


def _segment_layout(slot_height: float) -> tuple[int, float, float]:
    """Return segment count, segment height, and gap height for a keyed slot."""
    if slot_height <= 0.0:
        return 0, 0.0, 0.0

    ratio = _SEGMENT_GAP_RATIO
    min_h = _MIN_SEGMENT_PX
    count = 1
    seg_h = slot_height
    for n in range(1, 256):
        candidate = slot_height / (n + (n - 1) * ratio)
        if candidate < min_h:
            break
        count = n
        seg_h = candidate
    gap_h = seg_h * ratio
    return count, seg_h, gap_h


def _build_bar_history(
    frames: list[AudioBusFrame] | None,
    *,
    total: int,
    bar_count: int,
    sensitivity: float = 1.0,
) -> np.ndarray:
    history = np.zeros((total, bar_count), dtype=np.float32)
    if total == 0 or bar_count <= 0 or not frames:
        return history

    slices = _bar_bin_slices(bar_count)
    n = min(total, len(frames))
    raw = np.zeros((n, bar_count), dtype=np.float32)
    for f in range(n):
        frame = frames[f]
        freq = np.asarray(frame.spectrum, dtype=np.float32)
        raw[f] = _frame_to_bars(
            freq,
            slices,
            bass=float(frame.bass),
            mid=float(frame.mid),
            high=float(frame.high),
        )

    normalized = np.clip(_normalize_bar_timeline(raw) * float(sensitivity), 0.0, 1.0)
    s = float(_BUS_EMA_SMOOTHING)
    one_minus_s = 1.0 - s
    smoothed = np.zeros(bar_count, dtype=np.float32)
    for f in range(n):
        smoothed = smoothed * s + normalized[f] * one_minus_s
        history[f] = smoothed
    for f in range(n, total):
        smoothed *= s
        history[f] = smoothed
    return history


class MockupEq(AudioVisualMixin, ClipSkia):
    """Prepared mockup with a keyed display slot and a segmented multi-bar visualizer."""

    clip_type: ClassVar[str] = "std-mockup-eq"
    clip_category: ClassVar[ClipCategory] = ClipCategory.IMAGE
    clip_tags: ClassVar[list[str]] = [ClipTag.AUDIO_REACTIVE]

    source: str | None = Field(
        default=None, description="Local file path to a prepared mockup image"
    )
    key_color: Color = Field(
        default=_DEFAULT_KEY,
        json_schema_extra={"widget": "color"},
        description="Key color marking the display slot (flat fill, axis-aligned)",
    )
    bar_count: int = Field(
        default=5,
        ge=1,
        le=_MAX_BARS,
        multiple_of=1,
        description="Number of vertical bar columns in the keyed slot",
    )
    color: ColorToken | Color = color_field(ColorToken.PRIMARY)
    slot_background_mode: SlotBackgroundMode = Field(
        default=SlotBackgroundMode.TRANSPARENT,
        description="Slot fill: transparent or custom color",
    )
    slot_background: ColorToken | Color | None = Field(
        default=None,
        json_schema_extra={"widget": "color"},
        description="Slot fill color when mode is Custom",
    )
    opacity: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Overall layer opacity",
    )

    _image: skia.Image | None = PrivateAttr(default=None)
    _cover: _CoverFit | None = PrivateAttr(default=None)
    _primary_slot: Rect | None = PrivateAttr(default=None)
    _extra_slots: list[Rect] = PrivateAttr(default_factory=list)
    _bar_slices: list[tuple[int, int]] = PrivateAttr(default_factory=list)
    _bar_history: np.ndarray = PrivateAttr(
        default_factory=lambda: np.zeros((0, 0), dtype=np.float32)
    )

    @field_validator("slot_background_mode", mode="before")
    @classmethod
    def _coerce_legacy_mockup_mode(cls, v: object) -> object:
        if v == "mockup":
            return SlotBackgroundMode.TRANSPARENT
        return v

    @classmethod
    def source_upload_policy(cls) -> JobBoundsFactorPolicy:
        return JobBoundsFactorPolicy(factor=_MAX_DIM_FACTOR)

    @classmethod
    def source_max_px(cls, bounds: Rect) -> int:
        return cls.source_upload_policy().max_px_from_bounds(bounds.width, bounds.height)

    def _effective_slot_background_mode(self) -> SlotBackgroundMode:
        if self.slot_background_mode != SlotBackgroundMode.TRANSPARENT:
            return self.slot_background_mode
        if self.slot_background is not None:
            return SlotBackgroundMode.CUSTOM
        return SlotBackgroundMode.TRANSPARENT

    async def prepare(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        import asyncio

        await asyncio.to_thread(self._prepare_sync, ctx, bounds)

    def _prepare_sync(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        self._image = None
        self._cover = None
        self._primary_slot = None
        self._extra_slots = []
        self._bar_slices = _bar_bin_slices(self.bar_count)
        self._bar_history = _build_bar_history(
            self.bus_timeline(ctx),
            total=max(ctx.job.total_frames, 0),
            bar_count=self.bar_count,
            sensitivity=float(self.sensitivity),
        )

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
            log.warning("MockupEq %s: could not resolve source %r — %s", self.id, self.source, exc)
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
            log.warning("MockupEq %s: source file not found %r", self.id, local_path)
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
            log.warning("MockupEq %s: failed to load image %r — %s", self.id, local_path, exc)
            return

        b = bounds or Rect(0, 0, ctx.job.width, ctx.job.height)
        max_dim = self.source_max_px(b)

        if (
            not manifest_covers_max_px(local_path, max_dim)
            and max(pil_img.width, pil_img.height) > max_dim
        ):
            pil_img.thumbnail((max_dim, max_dim), PILImage.Resampling.LANCZOS)
            log.debug("MockupEq %s: downsampled to %dx%d", self.id, pil_img.width, pil_img.height)

        rgba = np.array(pil_img, dtype=np.uint8)
        key_mask = _color_match_mask(rgba, self.key_color, _KEY_TOLERANCE)
        mask = key_mask
        if _KEY_MASK_DILATE > 0:
            mask = ndimage.binary_dilation(mask, iterations=_KEY_MASK_DILATE)
        min_w = max(1, int(round(pil_img.width * _MIN_BLOB_FRAC)))
        min_h = max(1, int(round(pil_img.height * _MIN_BLOB_FRAC)))
        blobs = _find_blobs(mask, min_w=min_w, min_h=min_h)
        slot_blobs = _resolve_slot_blobs(
            rgba,
            self.key_color,
            min_w=min_w,
            min_h=min_h,
            dilated_blobs=blobs,
        )

        if not slot_blobs and not blobs:
            record_prepare_asset_failure(
                ctx,
                kind="clip",
                ref_id=self.id,
                clip_type=self.clip_type,
                field="key_color",
                source=self.key_color.hex,
                exc=ValueError("no key-color region found"),
                code="no_key_region",
            )
            log.warning("MockupEq %s: no qualifying key region for %s", self.id, self.key_color.hex)

        cover = _cover_fit(float(pil_img.width), float(pil_img.height), b)
        self._cover = cover

        if slot_blobs:
            mapped = [_map_blob_to_bounds(blob, cover) for blob in slot_blobs]
            self._primary_slot = mapped[0]
            self._extra_slots = mapped[1:]

        primary = blobs[0] if blobs else None
        keyed = _finalize_keyed_rgba(rgba, mask, primary)
        self._image = skia.Image.fromarray(keyed, colorType=skia.ColorType.kRGBA_8888_ColorType)

    def draw(self, ctx: RenderContext) -> None:
        if self._image is None or self._cover is None:
            return

        canvas: skia.Canvas = ctx.canvas
        bnd = ctx.bounds
        cover = self._cover
        src_w = float(self._image.width())
        src_h = float(self._image.height())

        paint = skia.Paint()
        paint.setAlphaf(self.opacity)

        canvas.save()
        canvas.clipRect(skia.Rect.MakeXYWH(bnd.x, bnd.y, float(bnd.width), float(bnd.height)))
        canvas.drawImageRect(
            self._image,
            skia.Rect.MakeWH(src_w, src_h),
            skia.Rect.MakeXYWH(cover.dx, cover.dy, cover.draw_w, cover.draw_h),
            skia.SamplingOptions(skia.FilterMode.kLinear),
            paint,
        )

        if self._primary_slot is not None:
            values = self._bar_values(ctx)
            for slot in (self._primary_slot, *self._extra_slots):
                self._draw_bars(canvas, ctx, slot, values)

        canvas.restore()

    def _bar_values(self, ctx: RenderContext) -> np.ndarray:
        n = self.bar_count
        if self._bar_history.size:
            frame = ctx.time.frame
            idx = max(0, min(frame, self._bar_history.shape[0] - 1))
            row = self._bar_history[idx]
            if row.shape[0] >= n:
                return row[:n]
        audio = self.audio(ctx)
        freq = np.asarray(audio.spectrum, dtype=np.float32)
        slices = self._bar_slices or _bar_bin_slices(n)
        bars = _frame_to_bars(
            freq,
            slices,
            bass=float(audio.bass),
            mid=float(audio.mid),
            high=float(audio.high),
        )
        return np.clip(bars * float(self.sensitivity), 0.0, 1.0)

    def _slot_fill_color(self, ctx: RenderContext) -> Color | None:
        mode = self._effective_slot_background_mode()
        if mode == SlotBackgroundMode.TRANSPARENT:
            return None
        if self.slot_background is not None:
            return resolve_color(self.slot_background, ctx.job.colors)
        return None

    def _draw_bars(
        self, canvas: skia.Canvas, ctx: RenderContext, slot: Rect, values: np.ndarray
    ) -> None:
        if slot.width <= 0.0 or slot.height <= 0.0:
            return

        fill = self._slot_fill_color(ctx)
        if fill is not None:
            br, bg_g, bb, ba = fill.rgba
            face_paint = skia.Paint(AntiAlias=False)
            face_paint.setARGB(int(ba * 255), int(br * 255), int(bg_g * 255), int(bb * 255))
            canvas.drawRect(
                skia.Rect.MakeXYWH(slot.x, slot.y, slot.width, slot.height),
                face_paint,
            )

        bar_columns = min(len(values), self.bar_count)
        if bar_columns <= 0:
            return

        segment_count, seg_h, gap_h = _segment_layout(slot.height)
        if segment_count <= 0 or seg_h <= 0.0:
            return

        resolved = resolve_color(self.color, ctx.job.colors)
        r, g, b, a = resolved.rgba
        bar_paint = skia.Paint(AntiAlias=True)
        bar_paint.setARGB(int(a * self.opacity * 255), int(r * 255), int(g * 255), int(b * 255))

        slot_w = slot.width / float(bar_columns)
        gap = slot_w * _BAR_GAP_RATIO
        bar_w = max(slot_w - gap, 1.0)
        bar_x_offset = gap * 0.5

        canvas.save()
        canvas.clipRect(skia.Rect.MakeXYWH(slot.x, slot.y, slot.width, slot.height))

        for index in range(bar_columns):
            value = max(0.0, min(1.0, float(values[index])))
            lit = int(round(value * segment_count))
            lit = max(0, min(segment_count, lit))
            if lit <= 0:
                continue

            bx = slot.x + index * slot_w + bar_x_offset
            for seg in range(lit):
                sy = slot.y + slot.height - (seg + 1) * seg_h - seg * gap_h
                canvas.drawRect(skia.Rect.MakeXYWH(bx, sy, bar_w, seg_h), bar_paint)

        canvas.restore()
