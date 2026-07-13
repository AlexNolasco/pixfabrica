"""Bounds-local Skia bad-signal tear — procedural + audio burst glitch."""

from __future__ import annotations

from typing import ClassVar

import numpy as np
import skia
from pydantic import Field, PrivateAttr

from pixfabrica_core.audio.bus import bus_timeline_for_select
from pixfabrica_core.clips import ClipCategory, ClipTag, PrepareContext
from pixfabrica_core.composition.effect_def import (
    EffectContext,
    SkiaEffect,
    resolve_effect_bus_select,
)
from pixfabrica_core.graphics import Rect
from pixfabrica_std_effects.effects._signal_envelope import (
    MAX_RGB_OFFSET_UV,
    MAX_SLICE_SHIFT_UV,
    band_height_px,
    hash1d,
    precompute_signal_envelope,
)

_MATRIX_R = [
    1.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    1.0,
    0.0,
]
_MATRIX_G = [
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    1.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    1.0,
    0.0,
]
_MATRIX_B = [
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    1.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    1.0,
    0.0,
]


def _skia_surface(w: int, h: int) -> skia.Surface:
    info = skia.ImageInfo.MakeN32Premul(max(1, w), max(1, h))
    surface = skia.Surface(info)
    if surface is None:
        raise RuntimeError(f"failed to allocate Skia surface {w}x{h}")
    return surface


def _render_sliced_bands(
    canvas: skia.Canvas,
    image: skia.Image,
    *,
    width: float,
    height: float,
    band_h: float,
    slice_shift_px: float,
    burst_seed: float,
) -> None:
    canvas.clear(skia.ColorTRANSPARENT)
    y = 0.0
    band_index = 0.0
    while y < height:
        bh = min(band_h, height - y)
        row_shift = (hash1d(band_index + burst_seed) - 0.5) * 2.0 * slice_shift_px
        canvas.save()
        canvas.clipRect(skia.Rect.MakeXYWH(0, y, width, bh))
        canvas.drawImage(image, row_shift, 0)
        canvas.restore()
        y += bh
        band_index += 1.0


def _draw_channel_pass(
    canvas: skia.Canvas,
    image: skia.Image,
    *,
    dx: float,
    matrix: list[float],
) -> None:
    paint = skia.Paint()
    paint.setColorFilter(skia.ColorFilters.Matrix(matrix))
    paint.setBlendMode(skia.BlendMode.kPlus)
    canvas.drawImage(image, dx, 0, paint=paint)


def _render_rgb_split(
    canvas: skia.Canvas,
    image: skia.Image,
    *,
    rgb_offset_px: float,
    rgb_sign: float,
) -> None:
    canvas.clear(skia.ColorTRANSPARENT)
    sign = float(rgb_sign)
    _draw_channel_pass(canvas, image, dx=rgb_offset_px * sign, matrix=_MATRIX_R)
    _draw_channel_pass(canvas, image, dx=0.0, matrix=_MATRIX_G)
    _draw_channel_pass(canvas, image, dx=-rgb_offset_px * sign, matrix=_MATRIX_B)


class SignalSkia(SkiaEffect):
    """Bad Signal — horizontal band tear with RGB split on audio and procedural bursts."""

    effect_type: ClassVar[str] = "std-signal-skia"
    clip_category: ClassVar[ClipCategory] = ClipCategory.EFFECTS
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED, ClipTag.AUDIO_REACTIVE]

    bus_select: str | None = Field(
        default=None,
        description="Bus for beat-triggered bursts; inherits parent bus when unset",
    )
    strength: float = Field(
        default=0.35,
        ge=0.0,
        le=1.0,
        multiple_of=0.05,
        description="RGB channel offset and row slice shift magnitude",
    )
    opacity: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Blend between original (0) and glitched (1)",
    )
    sensitivity: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Minimum amplitude gate for audio bursts (0 = all onsets)",
    )
    seed: int | None = Field(
        default=None,
        description="Random seed for burst schedule and variation; None derives from clip id",
    )

    _clip_start_frame: int = PrivateAttr(default=0)
    _intensity: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype=np.float32))
    _burst_seed: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype=np.float32))
    _rgb_sign: np.ndarray = PrivateAttr(default_factory=lambda: np.ones(0, dtype=np.float32))
    _slice_surface: skia.Surface | None = PrivateAttr(default=None)
    _glitch_surface: skia.Surface | None = PrivateAttr(default=None)
    _surface_size: tuple[int, int] = PrivateAttr(default=(0, 0))

    async def prepare(self, ctx: PrepareContext, _bounds: Rect | None = None) -> None:
        fps = float(ctx.job.fps)
        parent = ctx.parent_clip
        start_s = float(getattr(parent, "start", 0.0) or 0.0) if parent is not None else 0.0
        if parent is not None and parent.duration is not None:
            duration_s = float(parent.duration)
        else:
            duration_s = max(float(ctx.job.duration) - start_s, 0.0)

        clip_start_frame = round(start_s * fps)
        total_frames = max(round(duration_s * fps), 0)
        self._clip_start_frame = clip_start_frame

        bus_select = resolve_effect_bus_select(self, parent)
        bus_frames = None
        if (bus_select or "").strip():
            bus_frames = bus_timeline_for_select(ctx.audio, bus_select)

        self._intensity, self._burst_seed, self._rgb_sign = precompute_signal_envelope(
            total_frames=total_frames,
            fps=fps,
            clip_start_frame=clip_start_frame,
            clip_id=self.id,
            seed=self.seed,
            sensitivity=float(self.sensitivity),
            bus_select=bus_select,
            bus_frames=bus_frames,
        )

    def _ensure_surface(self, w: int, h: int, which: str) -> skia.Surface:
        iw, ih = max(1, int(w)), max(1, int(h))
        if self._surface_size != (iw, ih):
            self._slice_surface = None
            self._glitch_surface = None
            self._surface_size = (iw, ih)
        attr = "_slice_surface" if which == "slice" else "_glitch_surface"
        surf = getattr(self, attr)
        if surf is None:
            surf = _skia_surface(iw, ih)
            setattr(self, attr, surf)
        return surf

    def apply(self, ctx: EffectContext) -> None:
        image = ctx.source.makeImageSnapshot()
        canvas = ctx.target.getCanvas()
        canvas.clear(skia.ColorTRANSPARENT)

        w = float(ctx.bounds.width)
        h = float(ctx.bounds.height)
        if w <= 0.0 or h <= 0.0:
            return

        intensity_arr = self._intensity
        if intensity_arr.size == 0:
            canvas.drawImage(image, 0, 0)
            return

        local_f = int(ctx.time.frame) - self._clip_start_frame
        if local_f < 0 or local_f >= intensity_arr.shape[0]:
            canvas.drawImage(image, 0, 0)
            return

        intensity = float(intensity_arr[local_f])
        strength = float(self.strength)
        opacity = float(self.opacity)
        if intensity <= 0.0 or strength <= 0.0 or opacity <= 0.0:
            canvas.drawImage(image, 0, 0)
            return

        burst_seed = float(self._burst_seed[local_f])
        rgb_sign = float(self._rgb_sign[local_f])
        slice_shift_px = intensity * strength * MAX_SLICE_SHIFT_UV * w
        rgb_offset_px = intensity * strength * MAX_RGB_OFFSET_UV * w

        slice_surf = self._ensure_surface(int(w), int(h), "slice")
        _render_sliced_bands(
            slice_surf.getCanvas(),
            image,
            width=w,
            height=h,
            band_h=band_height_px(h),
            slice_shift_px=slice_shift_px,
            burst_seed=burst_seed,
        )
        sliced = slice_surf.makeImageSnapshot()

        glitch_surf = self._ensure_surface(int(w), int(h), "glitch")
        _render_rgb_split(
            glitch_surf.getCanvas(),
            sliced,
            rgb_offset_px=rgb_offset_px,
            rgb_sign=rgb_sign,
        )

        canvas.drawImage(image, 0, 0)
        paint = skia.Paint()
        paint.setAlphaf(min(1.0, max(0.0, intensity * opacity)))
        canvas.drawImage(glitch_surf.makeImageSnapshot(), 0, 0, paint=paint)
