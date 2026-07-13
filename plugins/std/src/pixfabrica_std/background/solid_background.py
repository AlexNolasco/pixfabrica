from __future__ import annotations

from typing import ClassVar

import skia
from pydantic import Field

from pixfabrica_core.clips import ClipCategory, ClipSkia, PrepareContext, RenderContext
from pixfabrica_core.graphics import Rect
from pixfabrica_core.theme.color import Color, ColorToken, color_field, resolve_color
from pixfabrica_std.tilt import (
    ANGLE_BAND_DESC,
    ANGLE_BAND_SKEW_MAX,
    ANGLE_BAND_SKEW_MIN,
    band_skew_px,
)


class SolidBackground(ClipSkia):
    """Fills a band of the clip bounds with a solid color and optional tilt."""

    clip_type: ClassVar[str] = "std-solid-background"
    clip_category: ClassVar[ClipCategory] = ClipCategory.BACKGROUND
    clip_tags: ClassVar[list[str]] = []
    color: ColorToken | Color = color_field(ColorToken.BACKGROUND)
    offset_y: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Band top edge as fraction of bounds height (0=top, 1=bottom)",
    )
    height: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Band thickness as fraction of bounds height",
    )
    angle: float = Field(
        default=0.0,
        ge=ANGLE_BAND_SKEW_MIN,
        le=ANGLE_BAND_SKEW_MAX,
        multiple_of=1.0,
        description=ANGLE_BAND_DESC,
    )
    opacity: float = Field(
        default=1.0, ge=0.0, le=1.0, multiple_of=0.1, description="Overall layer opacity"
    )

    async def prepare(self, _ctx: PrepareContext, _bounds: Rect | None = None) -> None:
        pass

    def draw(self, ctx: RenderContext) -> None:
        canvas: skia.Canvas = ctx.canvas
        b = ctx.bounds
        red, green, blue, alpha = resolve_color(self.color, ctx.job.colors).rgba

        paint = skia.Paint(AntiAlias=True)
        paint.setColor4f(skia.Color4f(red, green, blue, alpha * self.opacity))

        shift = band_skew_px(b.width, -self.angle)
        top_y = self.offset_y * b.height
        bot_y = top_y + self.height * b.height

        if self.height == 1.0:
            if shift > 0:
                bot_y += shift
            elif shift < 0:
                top_y += shift

        path = skia.Path()
        path.moveTo(b.x, b.y + top_y)  # top-left
        path.lineTo(b.x + b.width, b.y + top_y - shift)  # top-right
        path.lineTo(b.x + b.width, b.y + bot_y - shift)  # bottom-right
        path.lineTo(b.x, b.y + bot_y)  # bottom-left
        path.close()

        canvas.save()
        canvas.clipRect(skia.Rect.MakeXYWH(b.x, b.y, b.width, b.height))
        canvas.drawPath(path, paint)
        canvas.restore()
