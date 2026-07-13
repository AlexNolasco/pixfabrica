from __future__ import annotations

import math
from typing import ClassVar, Literal

import skia
from pydantic import Field, PrivateAttr

from pixfabrica_core.clips import ClipCategory, ClipSkia, ClipTag, PrepareContext, RenderContext
from pixfabrica_core.graphics import Rect
from pixfabrica_core.random import SeededRandom
from pixfabrica_core.theme.color import Color, ColorToken, color_field, resolve_color
from pixfabrica_std.tilt import (
    ANGLE_BAND_DESC,
    ANGLE_BAND_SKEW_MAX,
    ANGLE_BAND_SKEW_MIN,
    band_left_center_y,
    band_skew_px,
)


class SweepLines(ClipSkia):
    """Animated glowing lines sweeping across an angled band."""

    clip_type: ClassVar[str] = "std-sweep-lines"
    clip_category: ClassVar[ClipCategory] = ClipCategory.EFFECTS
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED, ClipTag.LOOP]

    color: ColorToken | Color = color_field(ColorToken.NEUTRAL)
    offset_y: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Band center as fraction of bounds height",
    )
    band_height: float = Field(
        default=0.15,
        ge=0.01,
        le=1.0,
        multiple_of=0.01,
        description="Band thickness as fraction of bounds height",
    )
    angle: float = Field(
        default=6.0,
        ge=ANGLE_BAND_SKEW_MIN,
        le=ANGLE_BAND_SKEW_MAX,
        multiple_of=1.0,
        description=ANGLE_BAND_DESC,
    )
    opacity: float = Field(
        default=0.4, ge=0.0, le=1.0, multiple_of=0.01, description="Overall layer opacity"
    )
    line_count: int = Field(
        default=3, ge=1, le=10, multiple_of=1, description="Number of sweeping lines"
    )
    line_width: int = Field(
        default=2, ge=0, le=16, multiple_of=1, description="Half-width of each line in pixels"
    )
    line_length: float = Field(
        default=1.0,
        ge=0.0,
        le=2.0,
        multiple_of=0.1,
        description="Line length as fraction of band diagonal (>1 extends past band edges)",
    )
    speed: float = Field(
        default=200.0,
        ge=0,
        le=1000,
        multiple_of=1,
        description="Sweep speed in px/s at output resolution",
    )
    glow: float = Field(
        default=0.0, ge=0.0, multiple_of=1.0, le=10, description="Glow blur sigma in pixels"
    )
    direction: Literal["left", "right"] = Field(default="left", description="Sweep direction")
    seed: int | None = Field(
        default=None, description="Random seed for line offsets; None derives from clip id"
    )

    # Precomputed in prepare() — zero allocations in draw()
    _clip_path: skia.Path = PrivateAttr()
    _line_template: skia.Path = PrivateAttr()
    _paint: skia.Paint = PrivateAttr()
    _glow_image: skia.Image | None = PrivateAttr(default=None)  # pre-baked glow, stamped each frame
    _glow_draw_paint: skia.Paint | None = PrivateAttr(default=None)
    _glow_img_ox: float = PrivateAttr(default=0.0)  # image center offset x
    _glow_img_oy: float = PrivateAttr(default=0.0)  # image center offset y
    _line_base_ys: list[float] = PrivateAttr(default_factory=list)
    _dx: float = PrivateAttr(default=0.0)
    _dy: float = PrivateAttr(default=0.0)
    _nx: float = PrivateAttr(default=0.0)
    _ny: float = PrivateAttr(default=0.0)
    _diag_len: float = PrivateAttr(default=0.0)
    _skew_px: float = PrivateAttr(default=0.0)
    _period: float = PrivateAttr(default=0.0)
    _spacing: float = PrivateAttr(default=0.0)
    _canvas_w: float = PrivateAttr(default=0.0)
    _half_len: float = PrivateAttr(default=0.0)

    async def prepare(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        b = bounds or Rect(0, 0, ctx.job.width, ctx.job.height)
        w, h = float(b.width), float(b.height)
        self._canvas_w = w

        # All geometry in bounds-local space (origin at b.x, b.y).
        # draw() translates the canvas to b.x, b.y so these coords land correctly.
        # Negate so +angle matches progress-bar / tilt convention (CW, up left→right).
        skew = band_skew_px(w, -self.angle)
        center_y = band_left_center_y(h, self.offset_y, skew)
        half_h = (self.band_height / 2) * h

        pts = [
            (0, center_y - half_h),
            (w, center_y - half_h - skew),
            (w, center_y + half_h - skew),
            (0, center_y + half_h),
        ]

        self._skew_px = pts[0][1] - pts[1][1]
        self._diag_len = math.sqrt(w * w + self._skew_px * self._skew_px)
        self._dx = w / self._diag_len
        self._dy = -self._skew_px / self._diag_len
        self._nx = -self._dy
        self._ny = self._dx
        self._half_len = (self.line_length * self._diag_len) / 2

        self._period = w + 2 * self._half_len
        self._spacing = self._period / self.line_count

        # Seeded random line positions within the band
        rng = (
            SeededRandom(self.seed) if self.seed is not None else SeededRandom.from_string(self.id)
        )
        band_px_h = pts[3][1] - pts[0][1]
        self._line_base_ys = [pts[0][1] + rng.next() * band_px_h for _ in range(self.line_count)]

        # Clip path — constant every frame
        self._clip_path = skia.Path()
        self._clip_path.moveTo(*pts[0])
        self._clip_path.lineTo(*pts[1])
        self._clip_path.lineTo(*pts[2])
        self._clip_path.lineTo(*pts[3])
        self._clip_path.close()

        # Line template centered at origin — constant every frame
        hl, pw = self._half_len, self.line_width
        dx, dy, nx, ny = self._dx, self._dy, self._nx, self._ny
        self._line_template = skia.Path()
        self._line_template.moveTo(-hl * dx - pw * nx, -hl * dy - pw * ny)
        self._line_template.lineTo(hl * dx - pw * nx, hl * dy - pw * ny)
        self._line_template.lineTo(hl * dx + pw * nx, hl * dy + pw * ny)
        self._line_template.lineTo(-hl * dx + pw * nx, -hl * dy + pw * ny)
        self._line_template.close()

        # Gradient in local space (centered at origin after translate) — constant every frame
        r, g, b, _ = resolve_color(self.color, ctx.job.colors).rgba
        shader = skia.GradientShader.MakeLinear(
            points=[(-pw * nx, -pw * ny), (pw * nx, pw * ny)],
            colors=[
                skia.Color4f(r, g, b, 0.0),
                skia.Color4f(r, g, b, self.opacity),
                skia.Color4f(r, g, b, 0.0),
            ],
            positions=[0.0, 0.5, 1.0],
        )

        self._paint = skia.Paint(AntiAlias=True)
        self._paint.setShader(shader)

        # Pre-bake glow into an offscreen image — blur runs once, not per frame.
        # Source is solid fill (alpha=1.0) so the blurred halo has maximum brightness.
        # Drawn additively (kPlus) so it accumulates light on dark backgrounds,
        # matching Canvas2D shadowBlur behavior.
        if self.glow > 0:
            spread = self.glow * 3
            ox = hl + spread
            oy = pw + spread
            img_w = int(ox * 2) + 2
            img_h = int(oy * 2) + 2
            self._glow_img_ox = ox
            self._glow_img_oy = oy

            bake_paint = skia.Paint(AntiAlias=True)
            bake_paint.setColor(skia.Color4f(r, g, b, 1.0))
            bake_paint.setImageFilter(skia.ImageFilters.Blur(self.glow, self.glow))

            surf = skia.Surface(img_w, img_h)
            c = surf.getCanvas()
            c.translate(ox, oy)
            c.drawPath(self._line_template, bake_paint)
            self._glow_image = surf.makeImageSnapshot()

            draw_paint = skia.Paint()
            draw_paint.setAlphaf(self.opacity)
            draw_paint.setBlendMode(skia.BlendMode.kPlus)
            self._glow_draw_paint = draw_paint
        else:
            self._glow_image = None
            self._glow_draw_paint = None

    def draw(self, ctx: RenderContext) -> None:
        canvas: skia.Canvas = ctx.canvas
        t = ctx.time.t
        travel = (t * ctx.job.scale_output_px(self.speed)) % self._period

        b = ctx.bounds
        canvas.save()
        canvas.translate(b.x, b.y)
        canvas.clipPath(self._clip_path, skia.ClipOp.kIntersect, True)

        for i in range(self.line_count):
            if self.direction == "left":
                x_pos = ((i * self._spacing + travel) % self._period) - self._half_len
            else:
                x_pos = (
                    self._canvas_w + self._half_len - ((i * self._spacing + travel) % self._period)
                )

            cx = x_pos
            cy = self._line_base_ys[i] - (self._skew_px / self._canvas_w) * x_pos

            if self._glow_image:
                canvas.drawImage(
                    self._glow_image,
                    cx - self._glow_img_ox,
                    cy - self._glow_img_oy,
                    paint=self._glow_draw_paint,
                )

            canvas.save()
            canvas.translate(cx, cy)
            canvas.drawPath(self._line_template, self._paint)
            canvas.restore()

        canvas.restore()
