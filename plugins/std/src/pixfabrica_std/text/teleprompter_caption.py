from __future__ import annotations

import logging
import math
from typing import ClassVar, Literal

import numpy as np
import skia
from pydantic import Field, PrivateAttr

from pixfabrica_core.clips import ClipCategory, ClipSkia, ClipTag, PrepareContext, RenderContext
from pixfabrica_core.graphics import Rect
from pixfabrica_core.lyrics import CaptionSegment
from pixfabrica_core.prepare_diagnostics import record_prepare_asset_failure
from pixfabrica_core.theme.color import Color, ColorToken, color_field, resolve_color
from pixfabrica_core.theme.typography import FontRole, FontSpec
from pixfabrica_std.text.lyrics_caption import (
    _parse,
    _resolve_source_sync,
    _WordItem,
    _wrap,
)
from pixfabrica_std.text.skia_font import make_typography_font

log = logging.getLogger("pixfabrica.std.teleprompter_caption")


def _find_active_index(segments: list[CaptionSegment], t: float) -> int | None:
    lo, hi = 0, len(segments) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        seg = segments[mid]
        if t < seg.start:
            hi = mid - 1
        elif t >= seg.end:
            lo = mid + 1
        else:
            return mid
    return None


def _scroll_target_index(segments: list[CaptionSegment], t: float) -> int:
    """Active index if inside a segment, otherwise the last passed index."""
    lo, hi = 0, len(segments) - 1
    last_passed = 0
    while lo <= hi:
        mid = (lo + hi) // 2
        seg = segments[mid]
        if t < seg.start:
            hi = mid - 1
        elif t >= seg.end:
            last_passed = mid
            lo = mid + 1
        else:
            return mid
    return last_passed


def _compute_layout(
    segments: list[CaptionSegment],
    font: skia.Font,
    space_w: float,
    max_w: float,
    line_h: float,
) -> tuple[list[tuple[list[list[_WordItem]], float]], list[float]]:
    """Returns (layout, cumulative_y).

    layout[i] = (wrapped_lines, segment_height)
    cumulative_y[i] = Y offset of segment i from top of the virtual column.
    """
    layout: list[tuple[list[list[_WordItem]], float]] = []
    cumulative: list[float] = [0.0]
    for seg in segments:
        items: list[_WordItem] = [(tok, None, font.measureText(tok)) for tok in seg.text.split()]
        lines = _wrap(items, space_w, max_w)
        height = max(len(lines), 1) * line_h
        layout.append((lines, height))
        cumulative.append(cumulative[-1] + height)
    return layout, cumulative


class TeleprompterCaption(ClipSkia):
    """Scrolling teleprompter-style caption.

    Shows multiple caption segments at once. The active segment is centered at
    offset_y and drawn in highlight_color; surrounding segments are dimmed.
    Smooth mode animates the scroll using exponential decay; snap mode cuts instantly.
    """

    clip_type: ClassVar[str] = "std-teleprompter-caption"
    clip_category: ClassVar[ClipCategory] = ClipCategory.TEXT
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED]

    source: str = Field(
        default="", description="Local path or http(s) URL to LRC, SRT, VTT, or WhisperX JSON"
    )
    typography_role: FontRole = Field(
        default="body_medium", description="Typography role from the job theme"
    )
    color: ColorToken | Color = color_field(ColorToken.NEUTRAL)
    highlight_color: ColorToken | Color = color_field(ColorToken.PRIMARY)
    placeholder: str = Field(
        default="", description="Text shown when no segment is active (between lines)"
    )
    lyrics_offset: float = Field(
        default=0.0,
        description="Shift lyric timings by this many seconds (positive = show later)",
    )
    offset_x: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Horizontal anchor (0=left, 1=right)",
    )
    offset_y: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Vertical anchor for the active line (0=top, 1=bottom)",
    )
    opacity: float = Field(default=1.0, ge=0.0, le=1.0, multiple_of=0.1)
    align: Literal["left", "center", "right"] = Field(default="center")
    wrap_width: float = Field(
        default=0.9,
        ge=0.1,
        le=1.0,
        multiple_of=0.1,
        description="Max text block width as fraction of bounds width",
    )
    context_lines: int = Field(
        default=2, ge=1, le=10, description="Segments visible above and below the active line"
    )
    dim_opacity: float = Field(
        default=0.4,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Opacity of non-active lines relative to opacity",
    )
    scroll_mode: Literal["snap", "smooth"] = Field(
        default="smooth",
        description="'smooth' animates scroll; 'snap' cuts instantly on segment change",
    )
    scroll_speed: float = Field(
        default=8.0,
        ge=0.5,
        le=30.0,
        multiple_of=0.1,
        description="Exponential decay rate for smooth scroll (higher = snappier)",
    )

    _segments: list[CaptionSegment] = PrivateAttr(default_factory=list)
    _prepare_key: tuple | None = PrivateAttr(default=None)
    _layout: list[tuple[list[list[_WordItem]], float]] | None = PrivateAttr(default=None)
    _cumulative_y: list[float] = PrivateAttr(default_factory=list)
    # Pre-computed scroll-Y per frame; draw() is stateless under parallel rendering.
    _scroll_history: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype="f4"))
    # Resolved font spec (cached so we don't rebuild Typeface in draw())
    _font_spec: FontSpec | None = PrivateAttr(default=None)
    _line_h: float = PrivateAttr(default=0.0)
    _space_w: float = PrivateAttr(default=0.0)
    _max_w: float = PrivateAttr(default=0.0)

    async def prepare(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        import asyncio

        if not self.source:
            return
        b = bounds or Rect(0, 0, ctx.job.width, ctx.job.height)
        key = (
            self.source,
            round(b.width, 1),
            self.typography_role,
            self.start,
            ctx.job.total_frames,
        )
        if key == self._prepare_key:
            return
        await asyncio.to_thread(self._prepare_sync, ctx, b)
        self._prepare_key = key

    def _prepare_sync(self, ctx: PrepareContext, bounds: Rect) -> None:
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
            log.warning(
                "TeleprompterCaption %s: could not resolve %r — %s", self.id, self.source, exc
            )
            return
        try:
            self._segments = _parse(path)
            log.debug("TeleprompterCaption %s: loaded %d segments", self.id, len(self._segments))
        except Exception as exc:
            log.warning("TeleprompterCaption %s: parse failed — %s", self.id, exc)
            return

        if not self._segments:
            return

        # Resolve font for layout + cache typography metrics for draw()
        spec: FontSpec = getattr(ctx.job.typography, self.typography_role)
        font = make_typography_font(spec)
        metrics = font.getMetrics()

        self._font_spec = spec
        self._line_h = (-metrics.fAscent + metrics.fDescent) * spec.line_height
        self._space_w = font.measureText(" ")
        self._max_w = bounds.width * self.wrap_width

        self._layout, self._cumulative_y = _compute_layout(
            self._segments, font, self._space_w, self._max_w, self._line_h
        )

        self._scroll_history = self._precompute_scroll(ctx.job.fps, ctx.job.total_frames)

    def _precompute_scroll(self, fps: float, total_frames: int) -> np.ndarray:
        """Roll the scroll EMA over the whole job timeline so draw() looks it up."""
        history = np.zeros(max(total_frames, 0), dtype="f4")
        if total_frames == 0 or not self._segments or self._layout is None:
            return history

        delta_t = 1.0 / fps
        alpha = 1.0 - math.exp(-self.scroll_speed * delta_t)
        scroll_y = 0.0
        primed = False
        for f in range(total_frames):
            t = f / fps
            lyrics_t = t - self.start + self.lyrics_offset
            target_idx = _scroll_target_index(self._segments, lyrics_t)
            seg_h = self._layout[target_idx][1]
            target_scroll_y = self._cumulative_y[target_idx] + seg_h / 2.0
            if self.scroll_mode == "snap" or not primed:
                scroll_y = target_scroll_y
                primed = True
            else:
                scroll_y += (target_scroll_y - scroll_y) * alpha
            history[f] = scroll_y
        return history

    def draw(self, ctx: RenderContext) -> None:
        if not self._segments or self._layout is None or self._font_spec is None:
            return

        canvas: skia.Canvas = ctx.canvas
        b = ctx.bounds
        lyrics_t = ctx.time.t - self.start + self.lyrics_offset

        spec = self._font_spec
        font = make_typography_font(spec)
        metrics = font.getMetrics()
        line_h = self._line_h
        space_w = self._space_w
        max_w = self._max_w

        active_idx = _find_active_index(self._segments, lyrics_t)
        target_idx = _scroll_target_index(self._segments, lyrics_t)

        # Stateless lookup: scroll trajectory pre-computed in prepare().
        if self._scroll_history.size:
            f_idx = max(0, min(ctx.time.frame, self._scroll_history.shape[0] - 1))
            scroll_y = float(self._scroll_history[f_idx])
        else:
            seg_h = self._layout[target_idx][1]
            scroll_y = self._cumulative_y[target_idx] + seg_h / 2.0

        anchor_y = b.y + self.offset_y * b.height
        block_x = b.x + (b.width - max_w) * self.offset_x

        # Paints
        r, g, bc, a = resolve_color(self.color, ctx.job.colors).rgba
        dim_paint = skia.Paint(AntiAlias=True)
        dim_paint.setColor4f(skia.Color4f(r, g, bc, a * self.opacity * self.dim_opacity))

        hr, hg, hb, ha = resolve_color(self.highlight_color, ctx.job.colors).rgba
        hl_paint = skia.Paint(AntiAlias=True)
        hl_paint.setColor4f(skia.Color4f(hr, hg, hb, ha * self.opacity))

        canvas.save()
        canvas.clipRect(skia.Rect.MakeXYWH(b.x, b.y, b.width, b.height))

        for i, (lines, seg_height) in enumerate(self._layout):
            seg_top = anchor_y - scroll_y + self._cumulative_y[i]

            # Skip segments outside visible bounds
            if seg_top + seg_height < b.y or seg_top > b.y + b.height:
                continue

            # Dim segments outside context_lines window (use target_idx — always valid)
            if abs(i - target_idx) > self.context_lines:
                continue

            is_active = i == active_idx
            paint = hl_paint if is_active else dim_paint

            y = seg_top
            for line in lines:
                line_w = sum(item[2] for item in line) + space_w * max(len(line) - 1, 0)
                match self.align:
                    case "left":
                        x = block_x
                    case "right":
                        x = block_x + max_w - line_w
                    case _:
                        x = block_x + (max_w - line_w) / 2.0

                baseline = y - metrics.fAscent
                for j, (word_text, _, word_w) in enumerate(line):
                    if j > 0:
                        x += space_w
                    canvas.drawString(word_text, x, baseline, font, paint)
                    x += word_w
                y += line_h

        # Placeholder drawn at anchor when between segments
        if active_idx is None and self.placeholder:
            items: list[_WordItem] = [
                (tok, None, font.measureText(tok)) for tok in self.placeholder.split()
            ]
            ph_lines = _wrap(items, space_w, max_w)
            ph_total_h = len(ph_lines) * line_h
            y = anchor_y - ph_total_h / 2.0
            for line in ph_lines:
                line_w = sum(item[2] for item in line) + space_w * max(len(line) - 1, 0)
                match self.align:
                    case "left":
                        x = block_x
                    case "right":
                        x = block_x + max_w - line_w
                    case _:
                        x = block_x + (max_w - line_w) / 2.0
                baseline = y - metrics.fAscent
                for j, (word_text, _, word_w) in enumerate(line):
                    if j > 0:
                        x += space_w
                    canvas.drawString(word_text, x, baseline, font, dim_paint)
                    x += word_w
                y += line_h

        canvas.restore()
