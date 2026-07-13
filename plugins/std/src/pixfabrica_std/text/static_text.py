from __future__ import annotations

from typing import ClassVar, Literal

import skia
from pydantic import Field

from pixfabrica_core.clips import ClipCategory, ClipSkia, PrepareContext, RenderContext
from pixfabrica_core.graphics import Rect
from pixfabrica_core.theme.color import Color, ColorToken, color_field, resolve_color
from pixfabrica_core.theme.typography import FontRole, FontSpec
from pixfabrica_std.text.skia_font import make_typography_font
from pixfabrica_std.tilt import ANGLE_FULL_DESC, ANGLE_FULL_MAX, ANGLE_FULL_MIN


class StaticText(ClipSkia):
    """Renders a single line of static text with configurable font, size, and color."""

    clip_type: ClassVar[str] = "std-static-text"
    clip_category: ClassVar[ClipCategory] = ClipCategory.TEXT
    clip_tags: ClassVar[list[str]] = []

    text: str = Field(default="{TITLE}", description="Text content to render")
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
        ge=ANGLE_FULL_MIN,
        le=ANGLE_FULL_MAX,
        multiple_of=1.0,
        description=ANGLE_FULL_DESC,
    )
    opacity: float = Field(
        default=1.0, ge=0.0, le=1.0, multiple_of=0.1, description="Overall layer opacity"
    )
    align: Literal["left", "center", "right"] = Field(
        default="center", description="Text alignment relative to the offset_x anchor"
    )

    async def prepare(self, _ctx: PrepareContext, _bounds: Rect | None = None) -> None:
        pass

    def draw(self, ctx: RenderContext) -> None:
        canvas: skia.Canvas = ctx.canvas
        b = ctx.bounds

        spec: FontSpec = getattr(ctx.job.typography, self.typography_role)
        font = make_typography_font(spec)

        metrics = font.getMetrics()
        lines = self.text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        line_height = -metrics.fAscent + metrics.fDescent

        x_anchor = b.x + self.offset_x * b.width
        y_anchor = b.y + self.offset_y * b.height

        # Center the whole block at the anchor; for a single line this reduces to
        # the original formula: y_anchor - (fAscent + fDescent) / 2
        first_baseline = y_anchor - (len(lines) * line_height) / 2.0 - metrics.fAscent

        r, g, bl, a = resolve_color(self.color, ctx.job.colors).rgba
        paint = skia.Paint(AntiAlias=True)
        paint.setColor4f(skia.Color4f(r, g, bl, a * self.opacity))

        canvas.save()
        canvas.clipRect(skia.Rect.MakeXYWH(b.x, b.y, b.width, b.height))
        if self.angle:
            canvas.rotate(self.angle, x_anchor, y_anchor)

        for i, line in enumerate(lines):
            line_width = font.measureText(line)
            match self.align:
                case "left":
                    x = x_anchor
                case "right":
                    x = x_anchor - line_width
                case _:
                    x = x_anchor - line_width / 2.0
            canvas.drawString(line, x, first_baseline + i * line_height, font, paint)

        canvas.restore()
