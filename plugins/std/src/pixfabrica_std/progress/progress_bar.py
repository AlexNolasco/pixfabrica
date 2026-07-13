from __future__ import annotations

from typing import ClassVar, Literal

import skia
from pydantic import Field

from pixfabrica_core.clips import ClipCategory, ClipSkia, ClipTag, PrepareContext, RenderContext
from pixfabrica_core.graphics import Rect
from pixfabrica_core.theme.color import Color, ColorPalette, ColorToken, color_field, resolve_color
from pixfabrica_core.theme.typography import FontRole
from pixfabrica_std.player._card_layout import ellipsize
from pixfabrica_std.progress._progress_common import (
    TimeMode,
    format_progress_time,
    playback_times,
    track_layout,
)
from pixfabrica_std.text.skia_font import make_typography_font
from pixfabrica_std.tilt import ANGLE_FULL_DESC, ANGLE_FULL_MAX, ANGLE_FULL_MIN

TextLayout = Literal["sides", "bottom", "none"]
IndicatorStyle = Literal["dot", "tick", "triangle"]


def _make_paint(color: Color, *, alpha_scale: float = 1.0) -> skia.Paint:
    r, g, b, a = color.rgba
    paint = skia.Paint(AntiAlias=True)
    paint.setColor4f(skia.Color4f(r, g, b, a * alpha_scale))
    return paint


def _resolve_paint(
    token: ColorToken | Color | None,
    palette: ColorPalette,
    *,
    base: Color,
    dim: float,
    opacity: float,
) -> skia.Paint:
    if token is not None:
        color = resolve_color(token, palette)
        return _make_paint(color, alpha_scale=opacity)
    return _make_paint(base, alpha_scale=dim * opacity)


class ProgressBar(ClipSkia):
    """Skia progress bar with optional elapsed/duration labels."""

    clip_type: ClassVar[str] = "std-progress-bar"
    clip_category: ClassVar[ClipCategory] = ClipCategory.PROGRESS
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED]

    time_mode: TimeMode = Field(
        default="clip",
        description="Clock source: clip window (start/duration) or full composition timeline",
    )
    text_layout: TextLayout = Field(
        default="sides",
        description="Label placement relative to the bar track",
    )
    typography_role: FontRole = Field(
        default="mono_small",
        description="Typography role from the job theme (ignored when text_layout=none)",
    )
    text_color: ColorToken | Color = color_field(ColorToken.PRIMARY)
    duration_color: ColorToken | Color | None = Field(
        default=None,
        description="Duration label color; None = dimmed text_color",
    )
    fill_color: ColorToken | Color | None = Field(
        default=None,
        description="Filled bar color; None = text_color",
    )
    track_color: ColorToken | Color | None = Field(
        default=None,
        description="Untraversed track color; None = dimmed text_color",
    )
    indicator_color: ColorToken | Color = color_field(ColorToken.ACCENT)
    text_dim_opacity: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.05,
        description="Opacity applied to text_color when duration/track colors are null",
    )
    indicator_style: IndicatorStyle = Field(
        default="dot",
        description="Playhead marker shape at the progress tip",
    )
    indicator_size: float = Field(
        default=1.5,
        ge=0.25,
        le=4.0,
        multiple_of=0.05,
        description="Indicator size as a multiplier of bar height",
    )
    text_gap: float = Field(
        default=0.015,
        ge=0.0,
        le=0.2,
        multiple_of=0.005,
        description="Gap between labels and bar as fraction of bounds height",
    )
    offset_y: float = Field(
        default=0.9,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Bar vertical position as fraction of bounds height (0=top, 1=bottom)",
    )
    offset_x: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Horizontal anchor as fraction of bounds width (0=left, 1=right)",
    )
    anchor_x: Literal["left", "center", "right"] = Field(
        default="center",
        description="How bar width expands from offset_x: left/right grow one way, center both",
    )
    width: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Bar length as a fraction of clip bounds width",
    )
    height: float = Field(
        default=0.004,
        ge=0.001,
        le=1.0,
        multiple_of=0.001,
        description="Bar thickness as fraction of bounds height",
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

    def _draw_indicator(
        self,
        canvas: skia.Canvas,
        *,
        cx: float,
        cy: float,
        bar_h: float,
        paint: skia.Paint,
    ) -> None:
        size = max(1.0, self.indicator_size * bar_h)
        half_h = bar_h / 2.0
        match self.indicator_style:
            case "dot":
                canvas.drawCircle(cx, cy, size / 2.0, paint)
            case "tick":
                half_len = max(half_h, size / 2.0)
                stroke = skia.Paint(paint)
                stroke.setStyle(skia.Paint.kStroke_Style)
                stroke.setStrokeWidth(max(1.0, bar_h * 0.2))
                canvas.drawLine(cx, cy - half_len, cx, cy + half_len, stroke)
            case "triangle":
                half_w = size / 2.0
                path = skia.Path()
                path.moveTo(cx - half_w, cy - half_h)
                path.lineTo(cx + half_w, cy - half_h)
                path.lineTo(cx, cy + half_h)
                path.close()
                canvas.drawPath(path, paint)

    def draw(self, ctx: RenderContext) -> None:
        canvas: skia.Canvas = ctx.canvas
        layout = track_layout(
            ctx.bounds,
            offset_x=self.offset_x,
            width=self.width,
            anchor_x=self.anchor_x,
        )
        if layout is None:
            return

        track_x, track_y, track_w, bounds_h = layout
        b = ctx.bounds
        w, h = float(b.width), float(b.height)

        elapsed, span, progress = playback_times(
            time_t=ctx.time.t,
            start=self.start,
            duration=self.duration,
            job_duration=ctx.job.duration,
            time_mode=self.time_mode,
        )

        bar_cy = track_y + self.offset_y * bounds_h
        bar_h = max(1.0, self.height * bounds_h)
        bar_half_h = bar_h / 2.0
        gap_px = self.text_gap * bounds_h

        base_color = resolve_color(self.text_color, ctx.job.colors)
        track_paint = _resolve_paint(
            self.track_color,
            ctx.job.colors,
            base=base_color,
            dim=self.text_dim_opacity,
            opacity=self.opacity,
        )
        fill_paint = _resolve_paint(
            self.fill_color,
            ctx.job.colors,
            base=base_color,
            dim=1.0,
            opacity=self.opacity,
        )
        elapsed_paint = _resolve_paint(
            None,
            ctx.job.colors,
            base=base_color,
            dim=1.0,
            opacity=self.opacity,
        )
        duration_paint = _resolve_paint(
            self.duration_color,
            ctx.job.colors,
            base=base_color,
            dim=self.text_dim_opacity,
            opacity=self.opacity,
        )
        indicator_paint = _resolve_paint(
            self.indicator_color,
            ctx.job.colors,
            base=base_color,
            dim=1.0,
            opacity=self.opacity,
        )

        font = make_typography_font(getattr(ctx.job.typography, self.typography_role))
        metrics = font.getMetrics()
        line_h = -metrics.fAscent + metrics.fDescent

        elapsed_str = format_progress_time(elapsed)
        duration_str = format_progress_time(span)

        track_left = track_x
        track_right = track_x + track_w
        bar_top = bar_cy - bar_half_h
        bar_bottom = bar_cy + bar_half_h

        min_x = track_left
        max_x = track_right
        min_y = bar_top
        max_y = bar_bottom

        if self.text_layout == "sides":
            left_max_w = max(0.0, track_left - b.x - gap_px)
            right_max_w = max(0.0, b.x + w - track_right - gap_px)
            elapsed_draw = ellipsize(elapsed_str, font, left_max_w)
            duration_draw = ellipsize(duration_str, font, right_max_w)
            if elapsed_draw:
                ew = font.measureText(elapsed_draw)
                min_x = min(min_x, track_left - gap_px - ew)
                min_y = min(min_y, bar_cy - line_h / 2.0)
                max_y = max(max_y, bar_cy + line_h / 2.0)
            if duration_draw:
                max_x = max(max_x, track_right + gap_px + font.measureText(duration_draw))
                min_y = min(min_y, bar_cy - line_h / 2.0)
                max_y = max(max_y, bar_cy + line_h / 2.0)
        elif self.text_layout == "bottom":
            text_top = bar_bottom + gap_px
            text_bottom = text_top + line_h
            min_y = min(min_y, text_top)
            max_y = max(max_y, text_bottom)
            elapsed_draw = ellipsize(elapsed_str, font, track_w / 2.0)
            duration_draw = ellipsize(duration_str, font, track_w / 2.0)
        else:
            elapsed_draw = ""
            duration_draw = ""

        pivot_x = (min_x + max_x) / 2.0
        pivot_y = (min_y + max_y) / 2.0

        canvas.save()
        canvas.clipRect(skia.Rect.MakeXYWH(b.x, b.y, w, h))
        if self.angle:
            canvas.rotate(self.angle, pivot_x, pivot_y)

        canvas.drawRect(
            skia.Rect.MakeXYWH(track_left, bar_top, track_w, bar_h),
            track_paint,
        )
        fill_w = track_w * progress
        if fill_w > 0.0:
            canvas.drawRect(skia.Rect.MakeXYWH(track_left, bar_top, fill_w, bar_h), fill_paint)

        tip_x = track_left + fill_w
        self._draw_indicator(
            canvas,
            cx=tip_x,
            cy=bar_cy,
            bar_h=bar_h,
            paint=indicator_paint,
        )

        if self.text_layout == "sides":
            baseline = bar_cy - line_h / 2.0 - metrics.fAscent
            if elapsed_draw:
                ew = font.measureText(elapsed_draw)
                canvas.drawString(
                    elapsed_draw, track_left - gap_px - ew, baseline, font, elapsed_paint
                )
            if duration_draw:
                canvas.drawString(
                    duration_draw, track_right + gap_px, baseline, font, duration_paint
                )
        elif self.text_layout == "bottom":
            baseline = bar_bottom + gap_px - metrics.fAscent
            if elapsed_draw:
                canvas.drawString(elapsed_draw, track_left, baseline, font, elapsed_paint)
            if duration_draw:
                dw = font.measureText(duration_draw)
                canvas.drawString(duration_draw, track_right - dw, baseline, font, duration_paint)

        canvas.restore()
