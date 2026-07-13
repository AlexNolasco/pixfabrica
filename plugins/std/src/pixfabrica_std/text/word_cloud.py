from __future__ import annotations

import logging
import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import ClassVar, Literal

import numpy as np
import skia
from pydantic import Field, PrivateAttr

from pixfabrica_core.clips import ClipCategory, ClipSkia, ClipTag, PrepareContext, RenderContext
from pixfabrica_core.graphics import Rect
from pixfabrica_core.prepare_diagnostics import record_prepare_asset_failure
from pixfabrica_core.random import SeededRandom, hash_string
from pixfabrica_core.theme.color import Color, ColorToken, color_field, resolve_color
from pixfabrica_core.theme.typography import FontRole, FontSpec
from pixfabrica_std.text.lyrics_caption import _parse, _resolve_source_sync
from pixfabrica_std.text.skia_font import make_typography_font
from pixfabrica_std.tilt import ANGLE_FULL_DESC, ANGLE_FULL_MAX, ANGLE_FULL_MIN

log = logging.getLogger("pixfabrica.std.word_cloud")

_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)


def _normalize_token(raw: str) -> str | None:
    cleaned = _PUNCT_RE.sub("", raw).lower()
    return cleaned or None


def _build_word_counts(
    segments: list,
    *,
    min_count: int,
    max_words: int,
) -> list[tuple[str, int]]:
    counter: Counter[str] = Counter()
    for seg in segments:
        for tok in seg.text.split():
            norm = _normalize_token(tok)
            if norm:
                counter[norm] += 1

    ranked = [(word, count) for word, count in counter.items() if count >= min_count]
    ranked.sort(key=lambda item: (-item[1], item[0]))
    return ranked[:max_words]


@dataclass(slots=True)
class _WordLayout:
    text: str
    count: int
    ratio: float
    speed: float
    font: skia.Font
    width: float
    ascent: float


def _angle_is_cardinal(angle: float) -> bool:
    return abs(math.remainder(angle, 360.0)) < 1e-6


def _drift_axes(
    direction: Literal["left", "right", "up", "down"],
    angle: float,
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Return drift and cross unit vectors. Cross points toward +screen-y at angle 0."""
    if _angle_is_cardinal(angle):
        match direction:
            case "right":
                return (1.0, 0.0), (0.0, 1.0)
            case "left":
                return (-1.0, 0.0), (0.0, 1.0)
            case "down":
                return (0.0, 1.0), (1.0, 0.0)
            case "up":
                return (0.0, -1.0), (1.0, 0.0)

    rad = math.radians(angle)
    baseline = (math.cos(rad), math.sin(rad))
    cross = (-math.sin(rad), math.cos(rad))
    match direction:
        case "right" | "left":
            return baseline, cross
        case "down" | "up":
            return cross, baseline


def _region_ts_bounds(
    region_w: float,
    region_h: float,
    drift_u: tuple[float, float],
    cross_u: tuple[float, float],
) -> tuple[float, float, float, float]:
    corners = ((0.0, 0.0), (region_w, 0.0), (region_w, region_h), (0.0, region_h))
    ts: list[float] = []
    ss: list[float] = []
    for cx, cy in corners:
        ts.append(cx * drift_u[0] + cy * drift_u[1])
        ss.append(cx * cross_u[0] + cy * cross_u[1])
    return min(ts), max(ts), min(ss), max(ss)


def _drift_region(
    width: float, height: float, padding: float, offset_x: float, offset_y: float
) -> tuple[float, float, float, float]:
    region_w = width * max(0.0, 1.0 - 2.0 * padding)
    region_h = height * max(0.0, 1.0 - 2.0 * padding)
    center_x = offset_x * width
    center_y = offset_y * height
    left = center_x - region_w / 2.0
    top = center_y - region_h / 2.0
    left = max(0.0, min(left, width - region_w))
    top = max(0.0, min(top, height - region_h))
    return left, top, region_w, region_h


def _simulate_trajectories_cardinal(
    layouts: list[_WordLayout],
    *,
    direction: Literal["left", "right", "up", "down"],
    region_left: float,
    region_top: float,
    region_w: float,
    region_h: float,
    fps: float,
    total_frames: int,
    clip_id: str,
    seed: int | None,
) -> tuple[np.ndarray, np.ndarray]:
    n = len(layouts)
    xs = np.zeros((max(total_frames, 0), n), dtype="f4")
    ys = np.zeros((max(total_frames, 0), n), dtype="f4")
    if total_frames == 0 or n == 0:
        return xs, ys

    spawn_seed = seed if seed is not None else hash_string(clip_id)
    positions_x = np.zeros(n, dtype="f4")
    positions_y = np.zeros(n, dtype="f4")
    wrap_counts = np.zeros(n, dtype=np.int32)
    dt = 1.0 / fps

    for i, layout in enumerate(layouts):
        word_rng = SeededRandom(hash_string(f"{spawn_seed}:{layout.text}:{i}"))
        glyph_h = -layout.ascent + layout.font.getMetrics().fDescent
        avail_h = max(region_h - glyph_h, 0.0)
        positions_x[i] = region_left + word_rng.next() * max(region_w - layout.width, 0.0)
        positions_y[i] = region_top - layout.ascent + word_rng.next() * avail_h

    region_right = region_left + region_w
    region_bottom = region_top + region_h

    for f in range(total_frames):
        xs[f] = positions_x
        ys[f] = positions_y

        for i, layout in enumerate(layouts):
            metrics = layout.font.getMetrics()
            glyph_h = -metrics.fAscent + metrics.fDescent
            word_rng = SeededRandom(
                hash_string(f"{spawn_seed}:{layout.text}:{i}:wrap:{wrap_counts[i]}")
            )

            match direction:
                case "right":
                    positions_x[i] += layout.speed * dt
                    if positions_x[i] > region_right:
                        positions_x[i] = region_left - layout.width
                        positions_y[i] = (
                            region_top
                            - metrics.fAscent
                            + word_rng.next() * max(region_h - glyph_h, 0.0)
                        )
                        wrap_counts[i] += 1
                case "left":
                    positions_x[i] -= layout.speed * dt
                    if positions_x[i] + layout.width < region_left:
                        positions_x[i] = region_right
                        positions_y[i] = (
                            region_top
                            - metrics.fAscent
                            + word_rng.next() * max(region_h - glyph_h, 0.0)
                        )
                        wrap_counts[i] += 1
                case "down":
                    positions_y[i] += layout.speed * dt
                    if positions_y[i] - metrics.fAscent > region_bottom:
                        positions_y[i] = region_top - metrics.fAscent
                        positions_x[i] = region_left + word_rng.next() * max(
                            region_w - layout.width, 0.0
                        )
                        wrap_counts[i] += 1
                case "up":
                    positions_y[i] -= layout.speed * dt
                    if positions_y[i] - metrics.fAscent + glyph_h < region_top:
                        positions_y[i] = region_bottom - metrics.fDescent
                        positions_x[i] = region_left + word_rng.next() * max(
                            region_w - layout.width, 0.0
                        )
                        wrap_counts[i] += 1

    return xs, ys


def _simulate_trajectories_oriented(
    layouts: list[_WordLayout],
    *,
    direction: Literal["left", "right", "up", "down"],
    angle: float,
    region_left: float,
    region_top: float,
    region_w: float,
    region_h: float,
    fps: float,
    total_frames: int,
    clip_id: str,
    seed: int | None,
) -> tuple[np.ndarray, np.ndarray]:
    n = len(layouts)
    xs = np.zeros((max(total_frames, 0), n), dtype="f4")
    ys = np.zeros((max(total_frames, 0), n), dtype="f4")
    if total_frames == 0 or n == 0:
        return xs, ys

    drift_u, cross_u = _drift_axes(direction, angle)
    t_lo, t_hi, s_lo, s_hi = _region_ts_bounds(region_w, region_h, drift_u, cross_u)
    forward = direction in ("right", "down")
    spawn_seed = seed if seed is not None else hash_string(clip_id)
    ts = np.zeros(n, dtype="f4")
    ss = np.zeros(n, dtype="f4")
    wrap_counts = np.zeros(n, dtype=np.int32)
    dt = 1.0 / fps

    for i, layout in enumerate(layouts):
        metrics = layout.font.getMetrics()
        glyph_h = -metrics.fAscent + metrics.fDescent
        word_rng = SeededRandom(hash_string(f"{spawn_seed}:{layout.text}:{i}"))
        t_span = max(t_hi - t_lo - layout.width, 0.0)
        s_span = max(s_hi - s_lo - glyph_h, 0.0)
        ts[i] = t_lo + word_rng.next() * t_span
        ss[i] = s_lo + word_rng.next() * s_span

    for f in range(total_frames):
        for i, layout in enumerate(layouts):
            metrics = layout.font.getMetrics()
            glyph_h = -metrics.fAscent + metrics.fDescent
            word_rng = SeededRandom(
                hash_string(f"{spawn_seed}:{layout.text}:{i}:wrap:{wrap_counts[i]}")
            )
            t_span = max(t_hi - t_lo - layout.width, 0.0)
            s_span = max(s_hi - s_lo - glyph_h, 0.0)

            if forward:
                ts[i] += layout.speed * dt
                if ts[i] + layout.width > t_hi:
                    ts[i] = t_lo - layout.width
                    ss[i] = s_lo + word_rng.next() * s_span
                    wrap_counts[i] += 1
            else:
                ts[i] -= layout.speed * dt
                if ts[i] < t_lo:
                    ts[i] = t_hi
                    ss[i] = s_lo + word_rng.next() * s_span
                    wrap_counts[i] += 1

            bx = region_left + ts[i] * drift_u[0] + (ss[i] - metrics.fAscent) * cross_u[0]
            by = region_top + ts[i] * drift_u[1] + (ss[i] - metrics.fAscent) * cross_u[1]
            xs[f, i] = bx
            ys[f, i] = by

    return xs, ys


def _simulate_trajectories(
    layouts: list[_WordLayout],
    *,
    direction: Literal["left", "right", "up", "down"],
    angle: float,
    region_left: float,
    region_top: float,
    region_w: float,
    region_h: float,
    fps: float,
    total_frames: int,
    clip_id: str,
    seed: int | None,
) -> tuple[np.ndarray, np.ndarray]:
    if _angle_is_cardinal(angle):
        return _simulate_trajectories_cardinal(
            layouts,
            direction=direction,
            region_left=region_left,
            region_top=region_top,
            region_w=region_w,
            region_h=region_h,
            fps=fps,
            total_frames=total_frames,
            clip_id=clip_id,
            seed=seed,
        )
    return _simulate_trajectories_oriented(
        layouts,
        direction=direction,
        angle=angle,
        region_left=region_left,
        region_top=region_top,
        region_w=region_w,
        region_h=region_h,
        fps=fps,
        total_frames=total_frames,
        clip_id=clip_id,
        seed=seed,
    )


class WordCloud(ClipSkia):
    """Kinetic lyrics word cloud sized and scrolled by word frequency.

    Aggregates all lines from a lyrics source into a frequency map, keeps the
    top words, and drifts them across the frame. Trajectories are pre-computed
    in prepare() for stateless parallel draw().
    """

    clip_type: ClassVar[str] = "std-word-cloud"
    clip_category: ClassVar[ClipCategory] = ClipCategory.TEXT
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED, ClipTag.LOOP]

    source: str = Field(
        default="", description="Local path or http(s) URL to LRC, SRT, VTT, or WhisperX JSON"
    )
    typography_role: FontRole = Field(
        default="body_medium", description="Typography role from the job theme"
    )
    color: ColorToken | Color = color_field(ColorToken.NEUTRAL)
    stroke_color: ColorToken | Color = color_field(ColorToken.PRIMARY)
    stroke_width: float = Field(
        default=0.04,
        ge=0.0,
        le=0.5,
        multiple_of=0.01,
        description="Stroke outline width as fraction of font size (0 = no stroke)",
    )
    offset_x: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Horizontal anchor of the drift region (0=left, 1=right)",
    )
    offset_y: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Vertical anchor of the drift region (0=top, 1=bottom)",
    )
    angle: float = Field(
        default=0.0,
        ge=ANGLE_FULL_MIN,
        le=ANGLE_FULL_MAX,
        multiple_of=1.0,
        description=ANGLE_FULL_DESC,
    )
    opacity: float = Field(default=1.0, ge=0.0, le=1.0, multiple_of=0.1)
    max_words: int = Field(
        default=40,
        ge=1,
        le=200,
        description="Maximum number of unique words to show (top by frequency)",
    )
    min_count: int = Field(
        default=1,
        ge=1,
        le=100,
        description="Minimum occurrences required for a word to appear",
    )
    size_scale: float = Field(
        default=1.0,
        ge=0.1,
        le=3.0,
        multiple_of=0.1,
        description="Scales font size relative to the most frequent word",
    )
    speed: float = Field(
        default=60.0,
        ge=0.0,
        le=500.0,
        multiple_of=1.0,
        description="Base drift speed in px/s at output resolution for the most frequent word",
    )
    direction: Literal["left", "right", "up", "down"] = Field(
        default="left",
        description=(
            "Drift direction; screen-aligned at 0°, otherwise relative to angle "
            "(left/right along the text axis, up/down perpendicular)"
        ),
    )
    padding: float = Field(
        default=0.05,
        ge=0.0,
        le=0.45,
        multiple_of=0.01,
        description="Inset of the drift region as a fraction of bounds width/height",
    )
    dim_opacity: float = Field(
        default=0.35,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Opacity of least frequent words relative to opacity (1.0 = uniform)",
    )
    seed: int | None = Field(
        default=None, description="Random seed for layout; None derives from clip id"
    )

    _layouts: list[_WordLayout] = PrivateAttr(default_factory=list)
    _xs: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros((0, 0), dtype="f4"))
    _ys: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros((0, 0), dtype="f4"))
    _prepare_key: tuple | None = PrivateAttr(default=None)

    async def prepare(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        import asyncio

        if not self.source:
            return
        b = bounds or Rect(0, 0, ctx.job.width, ctx.job.height)
        key = (
            self.source,
            round(b.width, 1),
            round(b.height, 1),
            self.typography_role,
            self.max_words,
            self.min_count,
            self.size_scale,
            self.speed,
            self.direction,
            self.padding,
            self.offset_x,
            self.offset_y,
            self.angle,
            self.opacity,
            self.stroke_width,
            self.seed,
            ctx.job.total_frames,
            ctx.job.fps,
        )
        if key == self._prepare_key:
            return
        await asyncio.to_thread(self._prepare_sync, ctx, b)
        self._prepare_key = key

    def _prepare_sync(self, ctx: PrepareContext, bounds: Rect) -> None:
        self._layouts = []
        self._xs = np.zeros((0, 0), dtype="f4")
        self._ys = np.zeros((0, 0), dtype="f4")

        try:
            path = _resolve_source_sync(self.source, ctx)
        except Exception as exc:
            record_prepare_asset_failure(
                ctx,
                kind="clip",
                ref_id=self.id,
                clip_type=self.clip_type,
                field="source",
                source=self.source,
                exc=exc,
            )
            log.warning("WordCloud %s: could not resolve %r — %s", self.id, self.source, exc)
            return

        try:
            segments = _parse(path)
            log.debug("WordCloud %s: loaded %d segments", self.id, len(segments))
        except Exception as exc:
            log.warning("WordCloud %s: parse failed — %s", self.id, exc)
            return

        ranked = _build_word_counts(segments, min_count=self.min_count, max_words=self.max_words)
        if not ranked:
            return

        spec: FontSpec = getattr(ctx.job.typography, self.typography_role)
        max_count = ranked[0][1]
        base_speed = ctx.job.scale_output_px(self.speed)

        layouts: list[_WordLayout] = []
        for word, count in ranked:
            ratio = count / max_count
            font_size = spec.size * ratio * self.size_scale
            font = make_typography_font(spec, subpixel=False)
            font.setSize(max(font_size, 1.0))
            font.setLinearMetrics(True)
            font.setHinting(skia.FontHinting.kNone)
            metrics = font.getMetrics()
            layouts.append(
                _WordLayout(
                    text=word,
                    count=count,
                    ratio=ratio,
                    speed=ratio * base_speed,
                    font=font,
                    width=font.measureText(word),
                    ascent=metrics.fAscent,
                )
            )

        region = _drift_region(
            bounds.width, bounds.height, self.padding, self.offset_x, self.offset_y
        )
        xs, ys = _simulate_trajectories(
            layouts,
            direction=self.direction,
            angle=self.angle,
            region_left=region[0],
            region_top=region[1],
            region_w=region[2],
            region_h=region[3],
            fps=ctx.job.fps,
            total_frames=ctx.job.total_frames,
            clip_id=self.id,
            seed=self.seed,
        )

        self._layouts = layouts
        self._xs = xs
        self._ys = ys

    def draw(self, ctx: RenderContext) -> None:
        if not self._layouts or self._xs.size == 0:
            return

        canvas: skia.Canvas = ctx.canvas
        b = ctx.bounds
        f_idx = max(0, min(ctx.time.frame, self._xs.shape[0] - 1))

        r, g, bc, a = resolve_color(self.color, ctx.job.colors).rgba
        fill_paint = skia.Paint(AntiAlias=True)

        if self.stroke_width > 0.0:
            skr, skg, skb, ska = resolve_color(self.stroke_color, ctx.job.colors).rgba
            stroke_paint = skia.Paint(AntiAlias=True)
            stroke_paint.setStyle(skia.Paint.kStroke_Style)
            stroke_paint.setStrokeCap(skia.Paint.kRound_Cap)
            stroke_paint.setStrokeJoin(skia.Paint.kRound_Join)
        else:
            stroke_paint = None
            skr = skg = skb = ska = 0.0

        canvas.save()
        canvas.clipRect(skia.Rect.MakeXYWH(b.x, b.y, b.width, b.height))

        frame_xs = self._xs[f_idx]
        frame_ys = self._ys[f_idx]

        for i, layout in enumerate(self._layouts):
            word_alpha = self.opacity * (self.dim_opacity + (1.0 - self.dim_opacity) * layout.ratio)
            fill_paint.setColor4f(skia.Color4f(r, g, bc, a * word_alpha))
            x = round(b.x + float(frame_xs[i]))
            y = round(b.y + float(frame_ys[i]))
            canvas.save()
            if self.angle:
                canvas.rotate(self.angle, x, y)
            if stroke_paint is not None:
                stroke_paint.setColor4f(skia.Color4f(skr, skg, skb, ska * word_alpha))
                sw = max(layout.font.getSize() * self.stroke_width, 0.5)
                stroke_paint.setStrokeWidth(sw)
                canvas.drawString(layout.text, x, y, layout.font, stroke_paint)
            canvas.drawString(layout.text, x, y, layout.font, fill_paint)
            canvas.restore()

        canvas.restore()
