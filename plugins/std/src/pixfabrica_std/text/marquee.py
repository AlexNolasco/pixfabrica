from __future__ import annotations

from typing import ClassVar, Literal

import skia
from pydantic import Field

from pixfabrica_core.clips import ClipCategory, ClipSkia, ClipTag, PrepareContext, RenderContext
from pixfabrica_core.graphics import Rect
from pixfabrica_core.theme.color import Color, ColorToken, color_field, resolve_color
from pixfabrica_core.theme.typography import FontRole, FontSpec
from pixfabrica_std.text.skia_font import make_typography_font
from pixfabrica_std.tilt import ANGLE_BAND_MAX, ANGLE_BAND_MIN, ANGLE_FULL_DESC


class Marquee(ClipSkia):
    """Continuously scrolling text band with optional tilt."""

    clip_type: ClassVar[str] = "std-marquee"
    clip_category: ClassVar[ClipCategory] = ClipCategory.TEXT
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED, ClipTag.SCROLLING, ClipTag.LOOP]

    text: str = Field(default="{TITLE}", description="Text content to scroll")
    typography_role: FontRole = Field(
        default="body_medium", description="Typography role from the job theme"
    )
    color: ColorToken | Color = color_field(ColorToken.NEUTRAL)
    offset_x: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Horizontal anchor as fraction of bounds width (0=left, 1=right)",
    )
    offset_y: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Vertical anchor as fraction of bounds height (0=top, 1=bottom)",
    )
    angle: float = Field(
        default=0.0,
        ge=ANGLE_BAND_MIN,
        le=ANGLE_BAND_MAX,
        multiple_of=1.0,
        description=ANGLE_FULL_DESC,
    )
    opacity: float = Field(default=1.0, ge=0.0, le=1.0, description="Overall layer opacity")
    speed: float = Field(
        default=100.0,
        ge=0,
        le=400,
        multiple_of=1,
        description="Scroll speed in px/s at output resolution",
    )
    direction: Literal["left", "right", "up", "down"] = Field(
        default="left", description="Scroll direction"
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
        text_width = font.measureText(self.text)
        text_height = -metrics.fAscent + metrics.fDescent
        gap = effective_size  # 1 em between repetitions

        r, g, bl, a = resolve_color(self.color, ctx.job.colors).rgba
        paint = skia.Paint(AntiAlias=True)
        paint.setColor4f(skia.Color4f(r, g, bl, a * self.opacity))
        if self.outline:
            paint.setStyle(skia.Paint.kStroke_Style)
            paint.setStrokeWidth(effective_size * self.outline_width)

        canvas.save()
        canvas.clipRect(skia.Rect.MakeXYWH(b.x, b.y, b.width, b.height))

        cx = b.x + self.offset_x * b.width
        cy = b.y + self.offset_y * b.height
        ref_x = b.x + b.width / 2.0
        ref_y = b.y + b.height / 2.0

        canvas.translate(cx, cy)
        if self.angle:
            canvas.rotate(self.angle)

        if self.direction in ("left", "right"):
            period = text_width + gap
            baseline = -(metrics.fAscent + metrics.fDescent) / 2.0
            left_local = b.x - ref_x
            right_local = b.x + b.width - ref_x

            scroll = (ctx.time.t * ctx.job.scale_output_px(self.speed)) % period
            x0 = left_local - scroll if self.direction == "left" else left_local - period + scroll
            while x0 > left_local:
                x0 -= period

            x = x0
            while x < right_local + text_width:
                canvas.drawString(self.text, x, baseline, font, paint)
                x += period

        else:  # up / down
            period = text_height + gap
            draw_x = -text_width / 2.0
            top_local = b.y - ref_y
            bottom_local = b.y + b.height - ref_y

            scroll = (ctx.time.t * ctx.job.scale_output_px(self.speed)) % period
            y0 = (
                top_local - metrics.fAscent - scroll
                if self.direction == "up"
                else top_local - metrics.fAscent - period + scroll
            )
            while y0 > top_local - metrics.fAscent:
                y0 -= period

            y = y0
            while y + metrics.fDescent < bottom_local + text_height:
                canvas.drawString(self.text, draw_x, y, font, paint)
                y += period

        canvas.restore()
