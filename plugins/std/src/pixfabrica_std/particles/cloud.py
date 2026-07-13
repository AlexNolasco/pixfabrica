from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from typing import ClassVar, Literal

import skia
from pydantic import Field, PrivateAttr

from pixfabrica_core.clips import (
    ClipCategory,
    ClipPreset,
    ClipSkia,
    ClipTag,
    PrepareContext,
    RenderContext,
)
from pixfabrica_core.graphics import Rect
from pixfabrica_core.random import SeededRandom, hash_string
from pixfabrica_core.theme.color import Color, ColorToken, color_field, resolve_color

# ── Stateless value noise (deterministic, no RNG per frame) ──────────────────


def _value_noise_1d(t: float, seed: float) -> float:
    """Smooth 1D value noise in [-1, 1]. Same as the TS version."""
    i0 = math.floor(t)
    i1 = i0 + 1
    f = t - i0

    def _hash(i: int) -> float:
        x = math.sin((i + seed * 131.7) * 127.1) * 43758.5453123
        return x - math.floor(x)

    u = f * f * (3.0 - 2.0 * f)  # smoothstep
    n0 = _hash(i0) * 2.0 - 1.0
    n1 = _hash(i1) * 2.0 - 1.0
    return n0 + (n1 - n0) * u


# ── Pre-computed blob data ───────────────────────────────────────────────────


@dataclass(slots=True)
class _SubBlob:
    dx: float
    dy: float
    r: float
    wobble_amp: float
    wobble_freq: float
    phase: float


@dataclass(slots=True)
class _CloudBlob:
    x: float
    y: float
    size: float
    vx: float
    vy: float
    layer: int
    subs: list[_SubBlob]
    breath_freq: float = 1.0  # oscillation Hz
    breath_phase: float = 0.0  # phase offset
    image: skia.Image | None = None  # pre-baked in prepare()
    img_cx: float = 0.0  # image center offset
    img_cy: float = 0.0


class Cloud(ClipSkia):
    """Animated cloud / fog field with organic sub-blob shapes."""

    clip_type: ClassVar[str] = "std-cloud"
    clip_category: ClassVar[ClipCategory] = ClipCategory.PARTICLES
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED, ClipTag.LOOP, ClipTag.PARTICLE]
    clip_presets: ClassVar[list[ClipPreset]] = [
        ClipPreset(
            id="heavy_fog",
            label="Heavy Fog",
            values={
                "amount": 25,
                "layers": 2,
                "speed": 2.0,
                "density": 0.9,
                "blur": 14.0,
                "opacity": 0.7,
                "direction": "wind",
                "wind_amp_x": 20.0,
                "wind_amp_y": 8.0,
            },
        ),
        ClipPreset(
            id="storm_clouds",
            label="Storm Clouds",
            values={
                "amount": 20,
                "layers": 6,
                "speed": 20.0,
                "density": 0.7,
                "blur": 6.0,
                "opacity": 0.8,
                "direction": "left",
                "wind_amp_x": 50.0,
                "wind_amp_y": 30.0,
            },
        ),
        ClipPreset(
            id="gentle_wisps",
            label="Gentle Wisps",
            values={
                "amount": 8,
                "layers": 3,
                "speed": 4.0,
                "density": 0.2,
                "blur": 12.0,
                "opacity": 0.3,
                "direction": "right",
                "wind_amp_x": 15.0,
                "wind_amp_y": 5.0,
            },
        ),
    ]

    color: ColorToken | Color = color_field(ColorToken.NEUTRAL_VARIANT)
    amount: int = Field(
        default=15, ge=1, le=32, multiple_of=1.0, description="Number of cloud blobs"
    )
    layers: int = Field(
        default=2, ge=1, le=8, multiple_of=1.0, description="Number of parallax depth layers"
    )
    speed: float = Field(
        default=5.0,
        ge=0.0,
        le=60,
        multiple_of=1.0,
        description="Drift speed in px/s at output resolution",
    )
    density: float = Field(
        default=0.6,
        ge=0.1,
        le=1.0,
        multiple_of=0.1,
        description="Sub-blob count per cloud (higher = fuller, rounder clouds)",
    )
    blur: float = Field(
        default=10.0,
        ge=0.0,
        le=16.0,
        multiple_of=1.0,
        description="Gaussian blur sigma applied to each blob",
    )
    opacity: float = Field(
        default=0.5, ge=0.0, le=1.0, multiple_of=0.1, description="Overall layer opacity"
    )
    direction: Literal["left", "right", "up", "down", "random", "wind"] = Field(
        default="right", description="Drift direction; 'wind' uses sinusoidal x/y oscillation"
    )
    wind_amp_x: float = Field(
        default=30.0,
        ge=0.0,
        multiple_of=1.0,
        le=60.0,
        description="Horizontal wind oscillation amplitude in pixels",
    )
    wind_amp_y: float = Field(
        default=12.0,
        ge=0.0,
        multiple_of=1.0,
        le=60.0,
        description="Vertical wind oscillation amplitude in pixels",
    )
    seed: int | None = Field(
        default=None, description="Random seed for blob layout; None derives from clip id"
    )

    _blobs: list[_CloudBlob] = PrivateAttr(default_factory=list)
    _canvas_w: float = PrivateAttr(default=0.0)
    _canvas_h: float = PrivateAttr(default=0.0)
    _draw_paint: skia.Paint = PrivateAttr()

    async def prepare(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        await asyncio.to_thread(self._prepare_sync, ctx, bounds)

    def _prepare_sync(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        b = bounds or Rect(0, 0, ctx.job.width, ctx.job.height)
        w, h = float(b.width), float(b.height)
        self._canvas_w = w
        self._canvas_h = h

        rng = (
            SeededRandom(self.seed) if self.seed is not None else SeededRandom.from_string(self.id)
        )

        max_size = h / 5.0
        r, g, bl, _ = resolve_color(self.color, ctx.job.colors).rgba
        wind_dir = self.direction
        scaled_speed = ctx.job.scale_output_px(self.speed)

        self._blobs = []
        for i in range(self.amount):
            layer = int(rng.next() * self.layers)
            size = rng.next() * max_size + max_size / 4.0
            x = rng.next() * w * 1.5 - w * 0.25
            y = rng.next() * h * 0.6 + h * 0.2

            base_speed = scaled_speed / (layer + 1)
            if wind_dir == "random":
                angle = rng.next() * math.tau
                vx = base_speed * math.cos(angle)
                vy = base_speed * math.sin(angle)
            elif wind_dir == "left":
                vx = -base_speed
                vy = 0.0
            elif wind_dir in ("right", "wind"):
                vx = base_speed
                vy = 0.0
                if wind_dir == "wind":
                    vx += (rng.next() * 2.0 - 1.0) * 1.5
                    vy = (rng.next() * 2.0 - 1.0) * 0.5
            elif wind_dir == "up":
                vx = 0.0
                vy = -base_speed
            else:  # down
                vx = 0.0
                vy = base_speed

            # Build sub-blobs (stable structure)
            sub_count = int(self.density * 4) + 5
            local_seed = hash_string(f"{self.id}:{i}")
            sub_rng = SeededRandom(local_seed)
            subs: list[_SubBlob] = []
            for _ in range(sub_count):
                subs.append(
                    _SubBlob(
                        dx=(sub_rng.next() * 0.8 - 0.4) * size,
                        dy=(sub_rng.next() * 0.5 - 0.25) * size,
                        r=size * (0.45 + sub_rng.next() * 0.55),
                        wobble_amp=size * (0.04 + sub_rng.next() * 0.08),
                        wobble_freq=0.05 + sub_rng.next() * 0.08,
                        phase=sub_rng.next() * math.tau,
                    )
                )

            blob = _CloudBlob(
                x=x,
                y=y,
                size=size,
                vx=vx,
                vy=vy,
                layer=layer,
                subs=subs,
                breath_freq=1.5 + rng.next() * 2.0,  # 1.5–3.5 Hz
                breath_phase=rng.next() * math.tau,
            )

            # Pre-bake this blob's shape into an image
            self._bake_blob(blob, r, g, bl)
            self._blobs.append(blob)

        # Sort back-to-front by layer
        self._blobs.sort(key=lambda b: b.layer)

        # Shared draw paint (blur is pre-baked into images)
        self._draw_paint = skia.Paint()
        self._draw_paint.setAlphaf(self.opacity)

    def _bake_blob(self, blob: _CloudBlob, r: float, g: float, b: float) -> None:
        """Render the blob's sub-ellipses at rest into an offscreen image, with blur pre-applied."""
        # Compute bounding box of all sub-blobs
        max_r = max(s.r + s.wobble_amp for s in blob.subs)
        min_x = min(s.dx for s in blob.subs) - max_r
        max_x = max(s.dx for s in blob.subs) + max_r
        min_y = min(s.dy for s in blob.subs) - max_r
        max_y = max(s.dy for s in blob.subs) + max_r

        # Extra padding for blur halo (3x sigma covers 99.7% of Gaussian)
        blur_pad = self.blur * 3.0 if self.blur > 0 else 0.0
        padding = 4.0 + blur_pad
        img_w = int(max_x - min_x + padding * 2) + 2
        img_h = int(max_y - min_y + padding * 2) + 2
        cx = -min_x + padding
        cy = -min_y + padding

        surf = skia.Surface(img_w, img_h)
        canvas = surf.getCanvas()
        canvas.clear(skia.ColorTRANSPARENT)

        for s in blob.subs:
            sx = cx + s.dx
            sy = cy + s.dy
            radius = max(2.0, s.r)

            shader = skia.GradientShader.MakeRadial(
                center=(sx, sy),
                radius=radius,
                colors=[
                    skia.Color4f(r, g, b, 1.0),
                    skia.Color4f(r, g, b, 0.85),
                    skia.Color4f(r, g, b, 0.0),
                ],
                positions=[0.0, 0.6, 1.0],
            )
            paint = skia.Paint(AntiAlias=True)
            paint.setShader(shader)
            canvas.drawCircle(sx, sy, radius, paint)

        # Apply blur to the entire blob image if requested
        raw = surf.makeImageSnapshot()
        if self.blur > 0:
            blurred_surf = skia.Surface(img_w, img_h)
            bc = blurred_surf.getCanvas()
            bc.clear(skia.ColorTRANSPARENT)
            bp = skia.Paint()
            bp.setImageFilter(skia.ImageFilters.Blur(self.blur, self.blur))
            bc.drawImage(raw, 0, 0, paint=bp)
            blob.image = blurred_surf.makeImageSnapshot()
        else:
            blob.image = raw
        blob.img_cx = cx
        blob.img_cy = cy

    def draw(self, ctx: RenderContext) -> None:
        canvas: skia.Canvas = ctx.canvas
        t = ctx.time.t
        b = ctx.bounds
        w, h = self._canvas_w, self._canvas_h

        canvas.save()
        canvas.translate(b.x, b.y)
        canvas.clipRect(skia.Rect.MakeWH(w, h))

        wind_ax = ctx.job.scale_output_px(self.wind_amp_x if self.direction != "wind" else 100.0)
        wind_ay = ctx.job.scale_output_px(self.wind_amp_y if self.direction != "wind" else 40.0)
        wind_t = t * 0.15

        for i, blob in enumerate(self._blobs):
            if blob.image is None:
                continue

            # Linear drift + wrap
            wrap_w = w * 1.5
            bx = (blob.x + blob.vx * t) % wrap_w - w * 0.25
            by = (blob.y + blob.vy * t) % h

            # Wind noise offset
            nx = _value_noise_1d(wind_t + i * 0.37, 17.0)
            ny = _value_noise_1d(wind_t + i * 0.53, 23.0)
            bx += nx * wind_ax
            by += ny * wind_ay

            # Per-blob breathing (scale oscillation)
            breath = 1.0 + 0.06 * math.sin(t * blob.breath_freq + blob.breath_phase)
            canvas.save()
            canvas.translate(bx, by)
            canvas.scale(breath, breath)
            canvas.drawImage(
                blob.image,
                -blob.img_cx,
                -blob.img_cy,
                paint=self._draw_paint,
            )
            canvas.restore()

        canvas.restore()
