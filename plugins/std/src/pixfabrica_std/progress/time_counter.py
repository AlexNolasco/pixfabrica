from __future__ import annotations

from typing import ClassVar

import skia
from pydantic import Field

from pixfabrica_core.clips import ClipCategory, ClipSkia, ClipTag, PrepareContext, RenderContext
from pixfabrica_core.graphics import Rect
from pixfabrica_core.theme.color import Color, ColorToken, color_field, resolve_color
from pixfabrica_core.theme.typography import FontRole, FontSpec
from pixfabrica_std.image.image_layout import ImageAlign, compute_text_draw_rect
from pixfabrica_std.progress._progress_common import (
    CounterDirection,
    TimeFormat,
    TimeMode,
    counter_display_seconds,
    format_counter_time,
    playback_times,
)
from pixfabrica_std.text.skia_font import make_typography_font
from pixfabrica_std.tilt import ANGLE_FULL_DESC, ANGLE_FULL_MAX, ANGLE_FULL_MIN


class TimeCounter(ClipSkia):
    """Skia monospace time counter with elapsed or remaining display."""

    clip_type: ClassVar[str] = "std-time-counter"
    clip_category: ClassVar[ClipCategory] = ClipCategory.PROGRESS
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED]

    time_mode: TimeMode = Field(
        default="clip",
        description="Clock source: clip window (start/duration) or full composition timeline",
    )
    direction: CounterDirection = Field(
        default="forward",
        description="Elapsed counts up from window start; remaining counts down to window end",
    )
    time_format: TimeFormat = Field(
        default="mm:ss",
        description="Fixed time display format (no auto-switching)",
    )
    typography_role: FontRole = Field(
        default="mono_small",
        description="Typography role from the job theme",
    )
    color: ColorToken | Color = color_field(ColorToken.PRIMARY)
    offset_x: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Horizontal bounds anchor as fraction of clip width (0=left, 1=right)",
    )
    offset_y: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Vertical bounds anchor as fraction of clip height (0=top, 1=bottom)",
    )
    align: ImageAlign = Field(
        default="center",
        description="Which point on the text bounding box attaches to the offset anchor",
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

    async def prepare(self, _ctx: PrepareContext, _bounds: Rect | None = None) -> None:
        pass

    def draw(self, ctx: RenderContext) -> None:
        canvas: skia.Canvas = ctx.canvas
        b = ctx.bounds
        w, h = float(b.width), float(b.height)
        bounds_rect = skia.Rect.MakeXYWH(b.x, b.y, w, h)

        elapsed, span, _progress = playback_times(
            time_t=ctx.time.t,
            start=self.start,
            duration=self.duration,
            job_duration=ctx.job.duration,
            time_mode=self.time_mode,
        )
        display_seconds = counter_display_seconds(elapsed, span, self.direction)
        text = format_counter_time(display_seconds, self.time_format)

        spec: FontSpec = getattr(ctx.job.typography, self.typography_role)
        font = make_typography_font(spec)
        metrics = font.getMetrics()
        line_h = -metrics.fAscent + metrics.fDescent
        text_w = font.measureText(text)

        x, y, draw_w, draw_h = compute_text_draw_rect(
            b,
            text_w=text_w,
            text_h=line_h,
            offset_x=self.offset_x,
            offset_y=self.offset_y,
            align=self.align,
        )
        if draw_w <= 0.0 or draw_h <= 0.0:
            return

        r, g, bl, a = resolve_color(self.color, ctx.job.colors).rgba
        paint = skia.Paint(AntiAlias=True)
        paint.setColor4f(skia.Color4f(r, g, bl, a))
        baseline = y - metrics.fAscent
        pivot_x = x + draw_w / 2.0
        pivot_y = y + draw_h / 2.0
        layer_active = self.opacity < 1.0

        canvas.save()
        canvas.clipRect(bounds_rect)
        if layer_active:
            layer_paint = skia.Paint()
            layer_paint.setAlphaf(self.opacity)
            canvas.saveLayer(bounds_rect, layer_paint)
        if self.angle:
            canvas.rotate(self.angle, pivot_x, pivot_y)
        canvas.drawString(text, x, baseline, font, paint)
        if layer_active:
            canvas.restore()
        canvas.restore()
