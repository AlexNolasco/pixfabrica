from __future__ import annotations

from typing import ClassVar, Literal

import skia
from pydantic import BaseModel, Field, model_validator

from pixfabrica_core.clips import ClipCategory, ClipSkia, ClipTag, PrepareContext, RenderContext
from pixfabrica_core.graphics import Rect
from pixfabrica_core.theme.color import Color, ColorToken, color_field, resolve_color
from pixfabrica_std.tilt import (
    ANGLE_BAND_DESC,
    ANGLE_BAND_SKEW_MAX,
    ANGLE_BAND_SKEW_MIN,
    band_skew_px,
)

GradientDirection = Literal[
    "to top",
    "to bottom",
    "to left",
    "to right",
    "to top right",
    "to bottom right",
    "to bottom left",
    "to top left",
]

# Maps direction → (start_x_frac, start_y_frac, end_x_frac, end_y_frac) within bounds
_DIR_POINTS: dict[str, tuple[float, float, float, float]] = {
    "to top": (0.5, 1.0, 0.5, 0.0),
    "to bottom": (0.5, 0.0, 0.5, 1.0),
    "to left": (1.0, 0.5, 0.0, 0.5),
    "to right": (0.0, 0.5, 1.0, 0.5),
    "to top right": (0.0, 1.0, 1.0, 0.0),
    "to bottom right": (0.0, 0.0, 1.0, 1.0),
    "to bottom left": (1.0, 0.0, 0.0, 1.0),
    "to top left": (1.0, 1.0, 0.0, 0.0),
}


class ColorStop(BaseModel):
    """One row in a linear gradient: color and optional 0–1 position (see ``color_stop_list`` in gen-ui)."""

    color: ColorToken | Color = color_field(ColorToken.PRIMARY)
    position: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="0–1 position along the gradient; evenly spaced if omitted",
    )


class Gradient(ClipSkia):
    """Linear gradient fill over a tilted band."""

    clip_type: ClassVar[str] = "std-gradient"
    clip_category: ClassVar[ClipCategory] = ClipCategory.BACKGROUND
    clip_tags: ClassVar[list[str]] = [ClipTag.GRADIENT, ClipTag.ANIMATED]

    color_stops: list[ColorStop] = Field(
        default_factory=list,
        max_length=3,
        description="Ordered color stops; positions auto-distributed if omitted",
    )
    direction: GradientDirection = Field(
        default="to bottom", description="Direction the gradient flows across the band"
    )
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
    opacity: float = Field(default=1.0, ge=0.0, le=1.0, description="Overall layer opacity")

    @model_validator(mode="after")
    def _resolve_positions(self) -> Gradient:
        n = len(self.color_stops)
        if n < 2:
            return self
        if any(s.position is None for s in self.color_stops):
            for i, stop in enumerate(self.color_stops):
                object.__setattr__(stop, "position", i / (n - 1))
        return self

    async def prepare(self, _ctx: PrepareContext, _bounds: Rect | None = None) -> None:
        pass

    def draw(self, ctx: RenderContext) -> None:
        if len(self.color_stops) < 2:
            return
        canvas: skia.Canvas = ctx.canvas
        b = ctx.bounds
        w, h = b.width, b.height

        shift = band_skew_px(w, -self.angle)
        top_y = self.offset_y * h
        visual_h = self.height * h
        bot_y = top_y + visual_h

        if self.height == 1.0:
            if shift > 0:
                bot_y += shift
            elif shift < 0:
                top_y += shift

        sx_f, sy_f, ex_f, ey_f = _DIR_POINTS[self.direction]
        start = (b.x + sx_f * w, b.y + self.offset_y * h + sy_f * visual_h)
        end = (b.x + ex_f * w, b.y + self.offset_y * h + ey_f * visual_h)

        colors = []
        positions = []
        for stop in self.color_stops:
            r, g, bl, a = resolve_color(stop.color, ctx.job.colors).rgba
            colors.append(skia.Color4f(r, g, bl, a * self.opacity))
            positions.append(float(stop.position))  # type: ignore[arg-type]

        shader = skia.GradientShader.MakeLinear(
            points=[start, end],
            colors=colors,
            positions=positions,
        )
        paint = skia.Paint(AntiAlias=True)
        paint.setShader(shader)

        path = skia.Path()
        path.moveTo(b.x, b.y + top_y)
        path.lineTo(b.x + w, b.y + top_y - shift)
        path.lineTo(b.x + w, b.y + bot_y - shift)
        path.lineTo(b.x, b.y + bot_y)
        path.close()

        canvas.save()
        canvas.clipRect(skia.Rect.MakeXYWH(b.x, b.y, w, h))
        canvas.drawPath(path, paint)
        canvas.restore()
