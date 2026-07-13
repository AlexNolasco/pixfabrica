from __future__ import annotations

from typing import ClassVar, Literal

import skia
from pydantic import Field

from pixfabrica_core.clips import ClipCategory, ClipSkia, ClipTag, PrepareContext, RenderContext
from pixfabrica_core.graphics import Rect
from pixfabrica_core.theme.color import Color, ColorToken, color_field, resolve_color
from pixfabrica_core.theme.typography import FontRole, FontSpec
from pixfabrica_std.text.skia_font import make_typography_font

_MAX_SWEEP_DEG = (
    359.9  # keep < 360 so Skia emits an arc, not a plain oval (which drops start_angle)
)


class PathMarquee(ClipSkia):
    """Text looping around a circular path, rotated to follow the curve's tangent."""

    clip_type: ClassVar[str] = "std-marquee-path"
    clip_category: ClassVar[ClipCategory] = ClipCategory.TEXT
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED, ClipTag.SCROLLING, ClipTag.LOOP]

    text: str = Field(default="{TITLE}", description="Text content to loop around the path")
    typography_role: FontRole = Field(
        default="body_medium", description="Typography role from the job theme"
    )
    color: ColorToken | Color = color_field(ColorToken.NEUTRAL)
    offset_x: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Circle center X as fraction of bounds width (0=left, 1=right)",
    )
    offset_y: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Circle center Y as fraction of bounds height (0=top, 1=bottom)",
    )
    radius: float = Field(
        default=0.35,
        ge=0.05,
        le=0.5,
        multiple_of=0.01,
        description="Circle radius as fraction of min(bounds.width, bounds.height)",
    )
    start_angle: float = Field(
        default=270.0,
        ge=0.0,
        le=360.0,
        multiple_of=1.0,
        description="Where the text loop starts, in degrees (0=3 o'clock, 90=6 o'clock, 270=12 o'clock)",
    )
    direction: Literal["cw", "ccw"] = Field(
        default="cw", description="Direction text travels around the circle"
    )
    opacity: float = Field(default=1.0, ge=0.0, le=1.0, description="Overall layer opacity")
    speed: float = Field(
        default=100.0,
        ge=0,
        le=400,
        multiple_of=1,
        description="Scroll speed in px/s of travel along the circumference at output resolution",
    )
    height_scale: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Scale font to this fraction of bounds height (0 = use FontRole size)",
    )
    outline: bool = Field(
        default=False,
        description="Draw text as stroke-only outline instead of filled",
    )
    outline_width: float = Field(
        default=0.05,
        ge=0.01,
        le=0.2,
        multiple_of=0.01,
        description="Stroke width as fraction of font size (only used when outline is enabled)",
    )

    async def prepare(self, _ctx: PrepareContext, _bounds: Rect | None = None) -> None:
        pass

    def draw(self, ctx: RenderContext) -> None:
        if not self.text:
            return
        canvas: skia.Canvas = ctx.canvas
        b = ctx.bounds

        spec: FontSpec = getattr(ctx.job.typography, self.typography_role)
        font = make_typography_font(spec)
        font.setLinearMetrics(True)
        font.setHinting(skia.FontHinting.kNone)

        effective_size = b.height * self.height_scale if self.height_scale > 0.0 else spec.size
        if self.height_scale > 0.0:
            font.setSize(effective_size)

        metrics = font.getMetrics()
        baseline_offset = -(metrics.fAscent + metrics.fDescent) / 2.0
        gap = effective_size  # 1 em between repetitions

        widths = [font.measureText(ch) for ch in self.text]
        text_width = sum(widths)
        if text_width <= 0:
            return
        min_period = text_width + gap

        radius = self.radius * min(b.width, b.height)
        if radius <= 0:
            return

        cx = b.x + self.offset_x * b.width
        cy = b.y + self.offset_y * b.height
        oval = skia.Rect.MakeXYWH(cx - radius, cy - radius, radius * 2.0, radius * 2.0)
        sweep = _MAX_SWEEP_DEG if self.direction == "cw" else -_MAX_SWEEP_DEG
        path = skia.Path()
        path.addArc(oval, self.start_angle, sweep)

        measure = skia.PathMeasure(path, True)
        length = measure.getLength()
        if length <= 0:
            return

        r, g, bl, a = resolve_color(self.color, ctx.job.colors).rgba
        paint = skia.Paint(AntiAlias=True)
        paint.setColor4f(skia.Color4f(r, g, bl, a * self.opacity))
        if self.outline:
            paint.setStyle(skia.Paint.kStroke_Style)
            paint.setStrokeWidth(effective_size * self.outline_width)

        # Snap the repeat count so copies tile the loop exactly — otherwise the
        # circumference is rarely an integer multiple of min_period and the
        # last copy overlaps the first at the seam where distance wraps to 0.
        reps = max(1, round(length / min_period))
        period = length / reps

        travel = (ctx.time.t * ctx.job.scale_output_px(self.speed)) % period

        canvas.save()
        canvas.clipRect(skia.Rect.MakeXYWH(b.x, b.y, b.width, b.height))

        for k in range(reps):
            base_dist = (travel + k * period) % length
            char_offset = 0.0
            for ch, w in zip(self.text, widths, strict=True):
                dist = (base_dist + char_offset) % length
                matrix = measure.getMatrix(dist)
                if matrix is not None:
                    canvas.save()
                    canvas.concat(matrix)
                    canvas.drawString(ch, 0, baseline_offset, font, paint)
                    canvas.restore()
                char_offset += w

        canvas.restore()
