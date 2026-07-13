"""Bounds-local Skia camera shake — organic jitter via seeded simplex noise."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import ClassVar

import skia
from pydantic import Field, PrivateAttr

from pixfabrica_core.clips import ClipCategory, ClipTag, PrepareContext
from pixfabrica_core.composition.effect_def import EffectContext, SkiaEffect
from pixfabrica_core.graphics import Rect
from pixfabrica_core.random import SeededRandom
from pixfabrica_std_effects._simplex import Simplex2D

# ── Tunable constants (Seriously.js camerashake defaults) ─────────────────────

OCTAVES = 2
AUTO_SCALE = True
PRE_SCALE = 0.0
MAX_SCALE = 1.0

AMP_X_RATIO = 1.0
AMP_Y_RATIO = 0.8

NOISE_ROT_Y = 7.0
NOISE_TRANS_X_Y = 11.0
NOISE_TRANS_Y_Y = 13.0


@dataclass(frozen=True)
class ShakeTransform:
    translate_x: float
    translate_y: float
    rotation_deg: float
    scale: float

    def is_identity(self, *, eps: float = 1e-9) -> bool:
        return (
            abs(self.translate_x) <= eps
            and abs(self.translate_y) <= eps
            and abs(self.rotation_deg) <= eps
            and abs(self.scale - 1.0) <= eps
        )


def _noise_delta(simplex: Simplex2D, t: float, t0: float, y_offset: float, freq: float) -> float:
    return simplex.noise2d(t * freq, y_offset * freq) - simplex.noise2d(t0 * freq, y_offset * freq)


def calc_auto_scale(width: float, height: float, x: float, y: float, angle_rad: float) -> float:
    """Zoom factor so translated/rotated content stays inside the clip bounds."""
    if width <= 0.0 or height <= 0.0:
        return 1.0

    scale = 1.0
    pi = math.pi
    angle = angle_rad - pi * math.floor(angle_rad / pi)

    if angle:
        sin_a = math.sin(angle)
        cos_a = math.sqrt(max(0.0, 1.0 - sin_a * sin_a))
        x0 = width / 2.0
        y0 = height / 2.0
        x1 = abs(x0 * cos_a - y0 * sin_a)
        y1 = abs(x0 * sin_a + y0 * cos_a)
        x2 = abs(-x0 * cos_a - y0 * sin_a)
        y2 = abs(-x0 * sin_a + y0 * cos_a)
        scale = 2.0 * max(x1 / width, x2 / width, y1 / height, y2 / height)

    scale *= max(
        (2.0 * abs(x) + width) / width,
        (2.0 * abs(y) + height) / height,
    )
    return scale


def compute_shake_transform(
    *,
    simplex: Simplex2D,
    time_s: float,
    time_origin_s: float,
    width: float,
    height: float,
    intensity: float,
    rotation: float,
    frequency: float,
    octaves: int = OCTAVES,
    amp_x_ratio: float = AMP_X_RATIO,
    amp_y_ratio: float = AMP_Y_RATIO,
    auto_scale: bool = AUTO_SCALE,
    pre_scale: float = PRE_SCALE,
    max_scale: float = MAX_SCALE,
) -> ShakeTransform:
    """Return pixel translate, rotation (degrees), and uniform scale for one frame."""
    if intensity <= 0.0 and rotation <= 0.0:
        return ShakeTransform(0.0, 0.0, 0.0, 1.0)

    t = time_s * frequency
    t0 = time_origin_s * frequency

    adjust = 0.0
    rotation_z = 0.0
    translate_x = 0.0
    translate_y = 0.0

    for i in range(max(1, octaves)):
        freq = 2.0**i
        amp = 0.5**i
        adjust += amp
        if rotation > 0.0:
            rotation_z += _noise_delta(simplex, t, t0, NOISE_ROT_Y, freq) * amp
        if intensity > 0.0:
            translate_x += _noise_delta(simplex, t, t0, NOISE_TRANS_X_Y, freq) * amp
            translate_y += _noise_delta(simplex, t, t0, NOISE_TRANS_Y_Y, freq) * amp

    if adjust <= 0.0:
        return ShakeTransform(0.0, 0.0, 0.0, 1.0)

    rotation_z *= rotation / adjust
    translate_x *= (intensity * amp_x_ratio) / adjust
    translate_y *= (intensity * amp_y_ratio) / adjust

    tx_px = translate_x * width
    ty_px = translate_y * height
    angle_rad = math.radians(rotation_z)

    scale = 1.0
    if auto_scale:
        if pre_scale >= 1.0:
            scale = max_scale
        else:
            dynamic = calc_auto_scale(width, height, tx_px, ty_px, angle_rad)
            scale = pre_scale * max_scale + (1.0 - pre_scale) * dynamic

    return ShakeTransform(tx_px, ty_px, rotation_z, scale)


class ShakeSkia(SkiaEffect):
    """Organic camera shake — center pivot, zero displacement at clip start time."""

    effect_type: ClassVar[str] = "std-shake-skia"
    clip_category: ClassVar[ClipCategory] = ClipCategory.EFFECTS
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED]

    intensity: float = Field(
        default=0.015,
        ge=0.0,
        le=0.08,
        multiple_of=0.001,
        description="Translation strength as a fraction of clip width/height",
    )
    rotation: float = Field(
        default=2.0,
        ge=0.0,
        le=12.0,
        multiple_of=0.1,
        description="Peak rotational jitter in degrees about center",
    )
    frequency: float = Field(
        default=1.5,
        ge=0.5,
        le=5.0,
        multiple_of=0.1,
        description="How quickly the shake evolves over time",
    )
    seed: int | None = Field(
        default=None,
        description="Random seed for shake pattern; None derives from clip id",
    )

    _simplex: Simplex2D | None = PrivateAttr(default=None)
    _time_origin: float = PrivateAttr(default=0.0)

    async def prepare(self, ctx: PrepareContext, _bounds: Rect | None = None) -> None:
        rng = (
            SeededRandom(self.seed) if self.seed is not None else SeededRandom.from_string(self.id)
        )
        self._simplex = Simplex2D(rng)
        parent = ctx.parent_clip
        raw_start = getattr(parent, "start", 0.0) if parent is not None else 0.0
        self._time_origin = float(raw_start or 0.0)

    def apply(self, ctx: EffectContext) -> None:
        image = ctx.source.makeImageSnapshot()
        canvas = ctx.target.getCanvas()
        canvas.clear(skia.ColorTRANSPARENT)

        w = float(ctx.bounds.width)
        h = float(ctx.bounds.height)
        if w <= 0.0 or h <= 0.0:
            return

        if self.intensity <= 0.0 and self.rotation <= 0.0:
            canvas.drawImage(image, 0, 0)
            return

        simplex = self._simplex
        if simplex is None:
            rng = (
                SeededRandom(self.seed)
                if self.seed is not None
                else SeededRandom.from_string(self.id)
            )
            simplex = Simplex2D(rng)

        transform = compute_shake_transform(
            simplex=simplex,
            time_s=float(ctx.time.t),
            time_origin_s=self._time_origin,
            width=w,
            height=h,
            intensity=float(self.intensity),
            rotation=float(self.rotation),
            frequency=float(self.frequency),
        )

        if transform.is_identity():
            canvas.drawImage(image, 0, 0)
            return

        cx = w / 2.0
        cy = h / 2.0
        canvas.save()
        canvas.translate(cx + transform.translate_x, cy + transform.translate_y)
        if transform.rotation_deg:
            canvas.rotate(transform.rotation_deg)
        if transform.scale != 1.0:
            canvas.scale(transform.scale, transform.scale)
        canvas.translate(-cx, -cy)
        canvas.drawImage(image, 0, 0)
        canvas.restore()
