from __future__ import annotations

from typing import ClassVar

import skia
from pydantic import Field

from pixfabrica_core.clips import ClipCategory, ClipSkia, ClipTag, PrepareContext, RenderContext
from pixfabrica_core.graphics import Rect
from pixfabrica_core.theme.color import Color, ColorPalette, ColorToken, color_field, resolve_color
from pixfabrica_std.progress._progress_common import TimeMode, playback_times
from pixfabrica_std.tilt import ANGLE_FULL_DESC, ANGLE_FULL_MAX, ANGLE_FULL_MIN

# Arc geometry (12 o'clock, clockwise).
_ARC_START_DEG = -90.0
_FULL_SWEEP_DEG = 360.0

# Inner dashed detail ring (tweak here; only ``dashed`` is exposed in the schema).
_INNER_RING_STROKE_RATIO = 0.35
_INNER_RING_RADIUS_INSET = 0.85
_INNER_RING_DASH_ON_RATIO = 0.015
_INNER_RING_DASH_GAP_RATIO = 0.0075
_INNER_RING_ALPHA = 0.25
_INNER_RING_STROKE_MIN_PX = 2.0

_GLOW_MIN_PX = 2.0
_GLOW_MAX_PX = 48.0


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


def ring_geometry(
    bounds: Rect,
    *,
    offset_x: float,
    offset_y: float,
    size: float,
) -> tuple[float, float, float, float] | None:
    """Return ``(cx, cy, radius, min_dim)`` in canvas space."""
    w, h = float(bounds.width), float(bounds.height)
    size_frac = max(0.0, min(float(size), 1.0))
    if size_frac <= 0.0:
        return None

    min_dim = min(w, h)
    cx = float(bounds.x) + min(max(float(offset_x), 0.0), 1.0) * w
    cy = float(bounds.y) + min(max(float(offset_y), 0.0), 1.0) * h
    radius = (size_frac * min_dim) / 2.0
    return cx, cy, radius, min_dim


def glow_blur_px(stroke_px: float, glow: float) -> float:
    """Map glow multiplier × stroke width to a clamped blur radius in px."""
    if glow <= 0.0:
        return 0.0
    raw = float(glow) * float(stroke_px)
    return max(_GLOW_MIN_PX, min(raw, _GLOW_MAX_PX))


class CircularProgress(ClipSkia):
    """Skia circular timeline scrubber with optional glow and dashed inner ring."""

    clip_type: ClassVar[str] = "std-circular-progress"
    clip_category: ClassVar[ClipCategory] = ClipCategory.PROGRESS
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED]

    time_mode: TimeMode = Field(
        default="clip",
        description="Clock source: clip window (start/duration) or full composition timeline",
    )
    color: ColorToken | Color = color_field(
        ColorToken.PRIMARY,
        description="Base ring color; fill and track fall back here when unset",
    )
    fill_color: ColorToken | Color | None = Field(
        default=None,
        description="Progress arc color; unset uses Color",
    )
    track_color: ColorToken | Color | None = Field(
        default=None,
        description="Background ring color; unset uses dimmed Color",
    )
    glow_color: ColorToken | Color | None = Field(
        default=None,
        description="Progress arc glow color; unset uses Fill Color",
    )
    track_dim_opacity: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.05,
        description="Dimming applied to Color when Track Color is unset",
    )
    track_visible: bool = Field(
        default=True,
        description="Draw the full background ring behind the progress arc",
    )
    stroke_width: float = Field(
        default=0.08,
        ge=0.01,
        le=0.35,
        multiple_of=0.01,
        description="Ring stroke thickness as a fraction of ring radius",
    )
    glow: float = Field(
        default=0.6,
        ge=0.0,
        le=4.0,
        multiple_of=0.05,
        description="Glow blur as a multiple of stroke width (clamped to a px range)",
    )
    dashed: bool = Field(
        default=False,
        description="Draw a decorative dashed inner ring using module constants",
    )
    offset_x: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Ring center horizontal position as fraction of bounds width",
    )
    offset_y: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Ring center vertical position as fraction of bounds height",
    )
    size: float = Field(
        default=0.2,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Ring diameter as a fraction of min(bounds width, height)",
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

    def _stroke_paint(
        self,
        ctx: RenderContext,
        *,
        token: ColorToken | Color | None,
        base: Color,
        dim: float,
        cap: int,
    ) -> skia.Paint:
        paint = _resolve_paint(
            token,
            ctx.job.colors,
            base=base,
            dim=dim,
            opacity=self.opacity,
        )
        paint.setStyle(skia.Paint.kStroke_Style)
        paint.setStrokeCap(cap)
        return paint

    def draw(self, ctx: RenderContext) -> None:
        canvas: skia.Canvas = ctx.canvas
        b = ctx.bounds
        w, h = float(b.width), float(b.height)

        geom = ring_geometry(
            b,
            offset_x=self.offset_x,
            offset_y=self.offset_y,
            size=self.size,
        )
        if geom is None:
            return

        cx, cy, radius, min_dim = geom
        if radius <= 1.0:
            return

        _, _, progress = playback_times(
            time_t=ctx.time.t,
            start=self.start,
            duration=self.duration,
            job_duration=ctx.job.duration,
            time_mode=self.time_mode,
        )

        stroke_px = max(1.0, self.stroke_width * radius)
        arc_r = radius - stroke_px / 2.0
        if arc_r <= 0.5:
            return

        base_color = resolve_color(self.color, ctx.job.colors)
        fill_base = (
            resolve_color(self.fill_color, ctx.job.colors) if self.fill_color else base_color
        )
        glow_token = self.glow_color if self.glow_color is not None else self.fill_color

        track_paint = self._stroke_paint(
            ctx,
            token=self.track_color,
            base=base_color,
            dim=self.track_dim_opacity,
            cap=skia.Paint.kButt_Cap,
        )
        track_paint.setStrokeWidth(stroke_px)

        fill_paint = self._stroke_paint(
            ctx,
            token=self.fill_color,
            base=base_color,
            dim=1.0,
            cap=skia.Paint.kRound_Cap,
        )
        fill_paint.setStrokeWidth(stroke_px)

        glow_paint: skia.Paint | None = None
        blur_px = glow_blur_px(stroke_px, self.glow)
        if progress > 0.001 and blur_px > 0.0:
            glow_base = (
                resolve_color(glow_token, ctx.job.colors) if glow_token is not None else fill_base
            )
            gr, gg, gb, ga = glow_base.rgba
            glow = skia.Paint(AntiAlias=True)
            glow.setStyle(skia.Paint.kStroke_Style)
            glow.setStrokeCap(skia.Paint.kRound_Cap)
            glow.setStrokeWidth(stroke_px)
            glow.setColor4f(skia.Color4f(gr, gg, gb, ga * self.opacity * 0.75))
            glow.setImageFilter(skia.ImageFilters.Blur(blur_px, blur_px))
            glow_paint = glow

        oval = skia.Rect(cx - arc_r, cy - arc_r, cx + arc_r, cy + arc_r)
        sweep_deg = _FULL_SWEEP_DEG * progress

        canvas.save()
        canvas.clipRect(skia.Rect.MakeXYWH(b.x, b.y, w, h))
        if self.angle:
            canvas.rotate(self.angle, cx, cy)

        if self.track_visible:
            canvas.drawCircle(cx, cy, arc_r, track_paint)

        if self.dashed:
            inner_sw = max(_INNER_RING_STROKE_MIN_PX, stroke_px * _INNER_RING_STROKE_RATIO)
            inner_r = arc_r - stroke_px * _INNER_RING_RADIUS_INSET
            if inner_r > inner_sw:
                fr, fg, fb, _ = fill_base.rgba
                inner_paint = skia.Paint(AntiAlias=True)
                inner_paint.setStyle(skia.Paint.kStroke_Style)
                inner_paint.setStrokeCap(skia.Paint.kButt_Cap)
                inner_paint.setStrokeWidth(inner_sw)
                inner_paint.setColor4f(skia.Color4f(fr, fg, fb, _INNER_RING_ALPHA * self.opacity))
                dash_on = min_dim * _INNER_RING_DASH_ON_RATIO
                dash_gap = min_dim * _INNER_RING_DASH_GAP_RATIO
                inner_paint.setPathEffect(skia.DashPathEffect.Make([dash_on, dash_gap], 0.0))
                inner_oval = skia.Rect(
                    cx - inner_r,
                    cy - inner_r,
                    cx + inner_r,
                    cy + inner_r,
                )
                canvas.drawArc(inner_oval, 0.0, _FULL_SWEEP_DEG, False, inner_paint)

        if progress > 0.001 and sweep_deg > 0.0:
            if glow_paint is not None:
                canvas.drawArc(oval, _ARC_START_DEG, sweep_deg, False, glow_paint)
            canvas.drawArc(oval, _ARC_START_DEG, sweep_deg, False, fill_paint)

        canvas.restore()


def arc_sweep_deg(progress: float) -> float:
    """Visible helper for tests: clockwise sweep in degrees from 12 o'clock."""
    return _FULL_SWEEP_DEG * min(max(float(progress), 0.0), 1.0)
