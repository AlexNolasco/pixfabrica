from __future__ import annotations

import math
from typing import ClassVar

import numpy as np
import skia
from pydantic import Field, PrivateAttr

from pixfabrica_core.audio.bus import AudioBusFrame
from pixfabrica_core.audio.mixin import AudioVisualMixin
from pixfabrica_core.clips import ClipCategory, ClipSkia, ClipTag, PrepareContext, RenderContext
from pixfabrica_core.graphics import Rect
from pixfabrica_core.theme.color import Color, ColorToken, resolve_color

DB_MIN = -20.0
DB_MAX = 3.0
DB_RANGE = DB_MAX - DB_MIN

# Cosmetic scale arc: lower-left (-20) through top (0 dB) to lower-right (+3).
_ARC_START_DEG = 210.0
_ARC_MID_DEG = 270.0
_ARC_END_DEG = 330.0
_ARC_SWEEP_DEG = _ARC_END_DEG - _ARC_START_DEG

DB_TICKS: tuple[int, ...] = (-20, -10, -7, -5, -3, -1, 0, 1, 2, 3)
PCT_TICKS: tuple[int, ...] = (0, 20, 40, 60, 80, 100)

ATTACK_TC_SEC = 0.10
RELEASE_TC_SEC = 0.45

_AMBER = Color("#E8C547")
_RED = Color("#FF2E2E")


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def level_to_db(level: float) -> float:
    return DB_MIN + _clamp01(level) * DB_RANGE


def db_to_skia_deg(db: float) -> float:
    db = max(DB_MIN, min(DB_MAX, db))
    if db <= 0.0:
        t = (db - DB_MIN) / -DB_MIN
        return _ARC_START_DEG + t * (_ARC_MID_DEG - _ARC_START_DEG)
    t = db / DB_MAX
    return _ARC_MID_DEG + t * (_ARC_END_DEG - _ARC_MID_DEG)


def pct_to_skia_deg(pct: float) -> float:
    t = _clamp01(pct / 100.0)
    return _ARC_START_DEG + t * (_ARC_MID_DEG - _ARC_START_DEG)


def level_to_skia_deg(level: float) -> float:
    return db_to_skia_deg(level_to_db(level))


def _point_on_circle(cx: float, cy: float, radius: float, skia_deg: float) -> tuple[float, float]:
    rad = math.radians(skia_deg)
    return cx + radius * math.cos(rad), cy + radius * math.sin(rad)


def _normalize_amplitudes(frames: list[AudioBusFrame], n: int) -> np.ndarray:
    """Stretch bus amplitude to ~0..1 using robust job-wide percentiles."""
    if n <= 0:
        return np.zeros(0, dtype=np.float32)
    raw = np.asarray([float(frames[f].amplitude) for f in range(n)], dtype=np.float32)
    lo, hi = np.percentile(raw, (5.0, 95.0))
    span = max(float(hi - lo), 1e-6)
    return np.clip((raw - lo) / span, 0.0, 1.0).astype(np.float32)


def _smooth_amplitude_timeline(
    frames: list[AudioBusFrame],
    total: int,
    *,
    fps: float,
    sensitivity: float,
) -> np.ndarray:
    """VU-ish asymmetric attack/release over normalized amplitude."""
    out = np.zeros(total, dtype=np.float32)
    if total <= 0:
        return out

    attack_alpha = 1.0 - math.exp(-1.0 / max(fps * ATTACK_TC_SEC, 1.0))
    release_alpha = 1.0 - math.exp(-1.0 / max(fps * RELEASE_TC_SEC, 1.0))
    norm = _normalize_amplitudes(frames, n := min(total, len(frames)))
    state = 0.0
    for f in range(n):
        target = _clamp01(float(norm[f]) * sensitivity)
        alpha = attack_alpha if target > state else release_alpha
        state += (target - state) * alpha
        out[f] = state
    for f in range(n, total):
        state += (0.0 - state) * release_alpha
        out[f] = state
    return out


def _meter_geometry(
    width: float,
    height: float,
    scale: float,
    offset_x: float,
    offset_y: float,
) -> tuple[float, float, float]:
    """Return needle pivot (cx, cy) and outer scale radius R."""
    size = min(width, height) * scale
    radius = size * 0.42
    cx = width * offset_x
    cy = height * offset_y
    return cx, cy, radius


class VuMeter(AudioVisualMixin, ClipSkia):
    """Classic analog-style VU meter driven by bus amplitude with VU ballistics."""

    clip_type: ClassVar[str] = "std-vu-meter"
    clip_category: ClassVar[ClipCategory] = ClipCategory.AUDIO
    clip_tags: ClassVar[list[str]] = [
        ClipTag.AUDIO_REACTIVE,
        ClipTag.ANIMATED,
        ClipTag.GLOW,
    ]

    color: ColorToken | Color = Field(
        default=_AMBER,
        json_schema_extra={"widget": "color"},
        description="Needle, ticks, and label color",
    )
    danger_color: ColorToken | Color = Field(
        default=_RED,
        json_schema_extra={"widget": "color"},
        description="Red clip band from 0 to +3 dB on the cosmetic scale",
    )
    scale: float = Field(
        default=1.0,
        ge=0.1,
        le=2.0,
        multiple_of=0.05,
        description="Uniform meter size within clip bounds",
    )
    offset_x: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Needle pivot horizontal position (0 = left, 0.5 = center, 1 = right)",
    )
    offset_y: float = Field(
        default=0.55,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Needle pivot vertical position (0 = top, 0.5 = center, 1 = bottom)",
    )
    opacity: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.05,
        description="Overall layer opacity",
    )
    glow: float = Field(
        default=4.0,
        ge=0.0,
        le=10.0,
        multiple_of=0.01,
        description="Glow blur sigma in pixels",
    )
    backdrop_opacity: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.05,
        description="Dark semicircular faceplate (0 = transparent)",
    )

    _needle_levels: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype=np.float32))
    _layout_w: float = PrivateAttr(default=0.0)
    _layout_h: float = PrivateAttr(default=0.0)
    _cx: float = PrivateAttr(default=0.0)
    _cy: float = PrivateAttr(default=0.0)
    _radius: float = PrivateAttr(default=0.0)
    _stroke_paint: skia.Paint = PrivateAttr()
    _danger_paint: skia.Paint = PrivateAttr()
    _glow_paint: skia.Paint | None = PrivateAttr(default=None)
    _backdrop_paint: skia.Paint | None = PrivateAttr(default=None)
    _needle_paint: skia.Paint = PrivateAttr()

    async def prepare(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        b = bounds or Rect(0, 0, ctx.job.width, ctx.job.height)
        self._layout_w = float(b.width)
        self._layout_h = float(b.height)
        self._cx, self._cy, self._radius = _meter_geometry(
            self._layout_w,
            self._layout_h,
            self.scale,
            self.offset_x,
            self.offset_y,
        )

        total = max(ctx.job.total_frames, 0)
        frames: list[AudioBusFrame] | None = self.bus_timeline(ctx)
        if frames and total > 0:
            self._needle_levels = _smooth_amplitude_timeline(
                frames,
                total,
                fps=float(ctx.job.fps),
                sensitivity=float(self.sensitivity),
            )
        else:
            self._needle_levels = np.zeros(total, dtype=np.float32)

        alpha = float(self.opacity)
        sr, sg, sb, _ = resolve_color(self.color, ctx.job.colors).rgba
        dr, dg, db_c, _ = resolve_color(self.danger_color, ctx.job.colors).rgba

        self._stroke_paint = skia.Paint(AntiAlias=True)
        self._stroke_paint.setStyle(skia.Paint.kStroke_Style)
        self._stroke_paint.setStrokeCap(skia.Paint.kRound_Cap)
        self._stroke_paint.setColor4f(skia.Color4f(sr, sg, sb, alpha))

        self._danger_paint = skia.Paint(AntiAlias=True)
        self._danger_paint.setStyle(skia.Paint.kStroke_Style)
        self._danger_paint.setStrokeCap(skia.Paint.kRound_Cap)
        self._danger_paint.setColor4f(skia.Color4f(dr, dg, db_c, alpha))

        self._needle_paint = skia.Paint(AntiAlias=True)
        self._needle_paint.setStyle(skia.Paint.kStroke_Style)
        self._needle_paint.setStrokeCap(skia.Paint.kRound_Cap)
        self._needle_paint.setStrokeWidth(max(1.2, self._radius * 0.018))
        self._needle_paint.setColor4f(skia.Color4f(sr, sg, sb, alpha))

        if self.glow > 0:
            glow = skia.Paint(AntiAlias=True)
            glow.setStyle(skia.Paint.kStroke_Style)
            glow.setStrokeCap(skia.Paint.kRound_Cap)
            glow.setColor4f(skia.Color4f(sr, sg, sb, alpha * 0.75))
            glow.setImageFilter(skia.ImageFilters.Blur(self.glow, self.glow))
            self._glow_paint = glow
        else:
            self._glow_paint = None

        if self.backdrop_opacity > 0:
            backdrop = skia.Paint(AntiAlias=True)
            backdrop.setStyle(skia.Paint.kFill_Style)
            backdrop.setColor4f(skia.Color4f(0.0, 0.0, 0.0, self.backdrop_opacity * alpha))
            self._backdrop_paint = backdrop
        else:
            self._backdrop_paint = None

    def draw(self, ctx: RenderContext) -> None:
        canvas: skia.Canvas = ctx.canvas
        b = ctx.bounds
        canvas.save()
        canvas.translate(b.x, b.y)

        cx, cy, radius = self._cx, self._cy, self._radius
        if radius <= 1.0:
            canvas.restore()
            return

        frame = ctx.time.frame
        if self._needle_levels.size:
            idx = max(0, min(frame, self._needle_levels.shape[0] - 1))
            level = float(self._needle_levels[idx])
        else:
            level = self.scale_audio(ctx.audio_bus_frame.amplitude)

        self._draw_backdrop(canvas, cx, cy, radius)
        self._draw_clip_band(canvas, cx, cy, radius)
        self._draw_scale_arcs(canvas, cx, cy, radius)
        self._draw_ticks(canvas, cx, cy, radius)
        self._draw_labels(canvas, cx, cy, radius)
        self._draw_needle(canvas, cx, cy, radius, level)

        canvas.restore()

    def _draw_backdrop(self, canvas: skia.Canvas, cx: float, cy: float, radius: float) -> None:
        if self._backdrop_paint is None:
            return
        path = skia.Path()
        oval = skia.Rect(cx - radius, cy - radius, cx + radius, cy + radius)
        path.addArc(oval, _ARC_START_DEG, _ARC_SWEEP_DEG)
        path.lineTo(cx, cy)
        path.close()
        canvas.drawPath(path, self._backdrop_paint)

    def _draw_clip_band(self, canvas: skia.Canvas, cx: float, cy: float, radius: float) -> None:
        r = radius * 0.94
        start = db_to_skia_deg(0.0)
        sweep = db_to_skia_deg(DB_MAX) - start
        band = skia.Paint(self._danger_paint)
        band.setStrokeWidth(max(3.0, radius * 0.055))
        path = skia.Path()
        path.addArc(skia.Rect(cx - r, cy - r, cx + r, cy + r), start, sweep)
        if self._glow_paint is not None:
            glow_band = skia.Paint(band)
            glow_band.setImageFilter(skia.ImageFilters.Blur(self.glow * 0.6, self.glow * 0.6))
            glow_band.setStrokeWidth(band.getStrokeWidth() * 1.4)
            canvas.drawPath(path, glow_band)
        canvas.drawPath(path, band)

    def _draw_scale_arcs(self, canvas: skia.Canvas, cx: float, cy: float, radius: float) -> None:
        db_r = radius * 0.98
        pct_r = radius * 0.86
        stroke = max(1.0, radius * 0.012)
        arc_paint = skia.Paint(self._stroke_paint)
        arc_paint.setStrokeWidth(stroke)

        for r in (db_r, pct_r):
            path = skia.Path()
            path.addArc(skia.Rect(cx - r, cy - r, cx + r, cy + r), _ARC_START_DEG, _ARC_SWEEP_DEG)
            if self._glow_paint is not None:
                canvas.drawPath(path, self._glow_paint)
            canvas.drawPath(path, arc_paint)

    def _draw_ticks(self, canvas: skia.Canvas, cx: float, cy: float, radius: float) -> None:
        compact = radius < 70.0
        db_outer = radius * 0.98
        db_inner = radius * 0.88
        pct_outer = radius * 0.86
        pct_inner = radius * 0.80
        tick_w = max(0.8, radius * 0.01)
        major_w = max(1.2, radius * 0.016)

        tick_paint = skia.Paint(self._stroke_paint)
        tick_paint.setStrokeWidth(tick_w)
        major_paint = skia.Paint(self._stroke_paint)
        major_paint.setStrokeWidth(major_w)

        for db in DB_TICKS:
            if compact and db not in (-20, -10, 0, 3):
                continue
            deg = db_to_skia_deg(float(db))
            is_major = db in (-20, -10, 0, 3) or db > 0
            paint = major_paint if is_major else tick_paint
            inner = db_inner if is_major else db_inner + (db_outer - db_inner) * 0.35
            x0, y0 = _point_on_circle(cx, cy, inner, deg)
            x1, y1 = _point_on_circle(cx, cy, db_outer, deg)
            canvas.drawLine(x0, y0, x1, y1, paint)

        for pct in PCT_TICKS:
            if compact and pct not in (0, 50, 100):
                continue
            deg = pct_to_skia_deg(float(pct))
            is_major = pct in (0, 100)
            paint = major_paint if is_major else tick_paint
            inner = pct_inner if is_major else pct_inner + (pct_outer - pct_inner) * 0.4
            x0, y0 = _point_on_circle(cx, cy, inner, deg)
            x1, y1 = _point_on_circle(cx, cy, pct_outer, deg)
            canvas.drawLine(x0, y0, x1, y1, paint)

    def _draw_labels(self, canvas: skia.Canvas, cx: float, cy: float, radius: float) -> None:
        compact = radius < 70.0
        db_font_size = max(7.0, radius * 0.095)
        pct_font_size = max(6.0, radius * 0.075)
        title_font_size = max(8.0, radius * 0.11)
        vu_font_size = max(10.0, radius * 0.14)

        db_font = skia.Font(skia.Typeface(), db_font_size)
        pct_font = skia.Font(skia.Typeface(), pct_font_size)
        title_font = skia.Font(skia.Typeface(), title_font_size)
        vu_font = skia.Font(skia.Typeface(), vu_font_size)

        text_paint = skia.Paint(self._stroke_paint)
        text_paint.setStyle(skia.Paint.kFill_Style)
        danger_text = skia.Paint(self._danger_paint)
        danger_text.setStyle(skia.Paint.kFill_Style)

        label_r_db = radius * 1.08
        label_r_pct = radius * 0.74

        for db in DB_TICKS:
            if compact and db not in (-20, -10, 0, 1, 2, 3):
                continue
            label = f"+{db}" if db > 0 else str(db)
            deg = db_to_skia_deg(float(db))
            lx, ly = _point_on_circle(cx, cy, label_r_db, deg)
            paint = danger_text if db > 0 else text_paint
            self._draw_centered_text(canvas, label, lx, ly, db_font, paint)

        for pct in PCT_TICKS:
            if compact and pct not in (0, 100):
                continue
            label = f"{pct}%"
            deg = pct_to_skia_deg(float(pct))
            lx, ly = _point_on_circle(cx, cy, label_r_pct, deg)
            self._draw_centered_text(canvas, label, lx, ly, pct_font, text_paint)

        title_y = cy - radius * 1.22
        self._draw_centered_text(canvas, "dB LEVEL", cx, title_y, title_font, text_paint)
        self._draw_centered_text(canvas, "VU", cx, cy + radius * 0.16, vu_font, text_paint)

    def _draw_centered_text(
        self,
        canvas: skia.Canvas,
        text: str,
        cx: float,
        cy: float,
        font: skia.Font,
        paint: skia.Paint,
    ) -> None:
        width = font.measureText(text)
        x = cx - width / 2.0
        y = cy + font.getSize() * 0.35
        if self._glow_paint is not None:
            glow_fill = skia.Paint(paint)
            glow_fill.setImageFilter(skia.ImageFilters.Blur(self.glow * 0.5, self.glow * 0.5))
            canvas.drawString(text, x, y, font, glow_fill)
        canvas.drawString(text, x, y, font, paint)

    def _draw_needle(
        self,
        canvas: skia.Canvas,
        cx: float,
        cy: float,
        radius: float,
        level: float,
    ) -> None:
        deg = level_to_skia_deg(level)
        tip_r = radius * 0.94
        hub_r = radius * 0.05
        x1, y1 = _point_on_circle(cx, cy, tip_r, deg)
        if self._glow_paint is not None:
            glow_needle = skia.Paint(self._needle_paint)
            glow_needle.setStrokeWidth(self._needle_paint.getStrokeWidth() * 2.5)
            glow_needle.setImageFilter(skia.ImageFilters.Blur(self.glow, self.glow))
            canvas.drawLine(cx, cy, x1, y1, glow_needle)
        canvas.drawLine(cx, cy, x1, y1, self._needle_paint)
        hub = skia.Paint(self._needle_paint)
        hub.setStyle(skia.Paint.kFill_Style)
        canvas.drawCircle(cx, cy, hub_r, hub)
