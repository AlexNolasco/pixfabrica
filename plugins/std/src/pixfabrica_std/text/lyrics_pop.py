from __future__ import annotations

import logging
from typing import ClassVar, Literal

import skia
from pydantic import Field, PrivateAttr

from pixfabrica_core.clips import ClipCategory, ClipSkia, ClipTag, PrepareContext, RenderContext
from pixfabrica_core.easing import ease_out
from pixfabrica_core.graphics import Rect
from pixfabrica_core.lyrics import CaptionSegment, CaptionWord
from pixfabrica_core.prepare_diagnostics import record_prepare_asset_failure
from pixfabrica_core.theme.color import Color, ColorToken, color_field, resolve_color
from pixfabrica_core.theme.typography import FontRole, FontSpec
from pixfabrica_std.text._text_utils import _case
from pixfabrica_std.text.lyrics_caption import (
    _find_active,
    _parse,
    _resolve_source_sync,
    _WordItem,
    _wrap,
)
from pixfabrica_std.text.skia_font import make_typography_font

log = logging.getLogger("pixfabrica.std.lyrics_pop")


class LyricsPop(ClipSkia):
    """Lyrics caption with a per-word pop-in animation and optional text stroke outline.

    Word-timing mode (when word timestamps are present, e.g. WhisperX JSON):
      - Words are invisible until their start time fires.
      - On fire: word scales down from (1 + scale_from) to 1.0 over
        max(word_dur * scale_duration_frac, 0.05s), eased with ease-out,
        rendered in color.
      - Once settled: word switches to highlight_color.

    Fallback (segment-only timing, e.g. LRC):
      - The whole segment scales in as one block.
      - Animating: color. Settled: highlight_color.
    """

    clip_type: ClassVar[str] = "std-lyrics-pop"
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
    stroke_color: ColorToken | Color = color_field(ColorToken.BACKGROUND)
    stroke_width: float = Field(
        default=0.03,
        ge=0.0,
        le=0.5,
        multiple_of=0.1,
        description="Stroke outline width as fraction of font size (0 = no stroke)",
    )
    scale_from: float = Field(
        default=0.2,
        ge=0.0,
        le=2.0,
        multiple_of=0.1,
        description="Entry scale overshoot above 1.0 (e.g., 0.2 = starts 20% larger than normal)",
    )
    scale_duration_frac: float = Field(
        default=0.2,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Fraction of segment duration over which the scale-down animation runs",
    )
    min_word_anim: float = Field(
        default=0.05,
        ge=0.0,
        multiple_of=0.01,
        description="Minimum per-word animation duration in seconds (floor for fast lyrics)",
    )
    placeholder: str = Field(
        default="", description="Text shown between caption lines; empty = show nothing"
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
        description="Horizontal anchor (0=left edge, 1=right edge)",
    )
    offset_y: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Vertical anchor (0=top, 1=bottom)",
    )
    opacity: float = Field(
        default=1.0, ge=0.0, le=1.0, multiple_of=0.1, description="Overall layer opacity"
    )
    align: Literal["left", "center", "right"] = Field(
        default="center", description="Text alignment within the wrap block"
    )
    wrap_width: float = Field(
        default=0.9,
        ge=0.1,
        le=1.0,
        multiple_of=0.1,
        description="Max text block width as fraction of bounds width",
    )
    text_case: Literal["as_is", "upper", "lower"] = Field(
        default="as_is", description="Transform text case before rendering"
    )

    _segments: list[CaptionSegment] = PrivateAttr(default_factory=list)
    _prepare_key: tuple | None = PrivateAttr(default=None)
    _font: skia.Font | None = PrivateAttr(default=None)
    _metrics: skia.FontMetrics | None = PrivateAttr(default=None)
    _spec: FontSpec | None = PrivateAttr(default=None)
    _space_w: float = PrivateAttr(default=0.0)

    async def prepare(self, ctx: PrepareContext, _bounds: Rect | None = None) -> None:
        import asyncio

        if not self.source:
            return
        key = (self.source, self.typography_role)
        if key == self._prepare_key:
            return
        await asyncio.to_thread(self._prepare_sync, ctx)
        self._prepare_key = key

    def _prepare_sync(self, ctx: PrepareContext) -> None:
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
            log.warning("LyricsPop %s: could not resolve %r — %s", self.id, self.source, exc)
            return
        try:
            self._segments = _parse(path)
            log.debug("LyricsPop %s: loaded %d segments", self.id, len(self._segments))
        except Exception as exc:
            log.warning("LyricsPop %s: parse failed — %s", self.id, exc)

        spec: FontSpec = getattr(ctx.job.typography, self.typography_role)
        font = make_typography_font(spec)
        self._spec = spec
        self._font = font
        self._metrics = font.getMetrics()
        self._space_w = font.measureText(" ")

    def draw(self, ctx: RenderContext) -> None:
        canvas: skia.Canvas = ctx.canvas
        b = ctx.bounds

        lyrics_t = ctx.time.t - self.start + self.lyrics_offset
        seg = _find_active(self._segments, lyrics_t) if self._segments else None

        text = _case(seg.text, self.text_case) if seg else self.placeholder
        if not text:
            return

        words = seg.words if seg else ()
        use_word_timing = bool(words) and self.scale_from > 0.0 and self.scale_duration_frac > 0.0

        # Synthesize per-word timing from segment duration when no word timestamps exist
        if (
            not use_word_timing
            and seg is not None
            and self.scale_from > 0.0
            and self.scale_duration_frac > 0.0
        ):
            tokens = text.split()
            if tokens:
                n = len(tokens)
                slot = (seg.end - seg.start) / n
                words = tuple(
                    CaptionWord(
                        start=seg.start + i * slot, end=seg.start + (i + 1) * slot, word=tok
                    )
                    for i, tok in enumerate(tokens)
                )
                use_word_timing = True

        if self._font is None or self._metrics is None or self._spec is None:
            return
        font = self._font
        metrics = self._metrics
        spec = self._spec
        space_w = self._space_w

        line_h = (-metrics.fAscent + metrics.fDescent) * spec.line_height
        max_w = b.width * self.wrap_width
        glyph_h = -metrics.fAscent + metrics.fDescent

        if use_word_timing:
            items: list[_WordItem] = [
                (t := _case(w.word, self.text_case), i, font.measureText(t))
                for i, w in enumerate(words)
            ]
        else:
            items = [(tok, None, font.measureText(tok)) for tok in text.split()]

        lines = _wrap(items, space_w, max_w)
        total_h = len(lines) * line_h

        block_x = b.x + (b.width - max_w) * self.offset_x
        center_y = b.y + self.offset_y * b.height
        y = center_y - total_h / 2.0

        actual_w = max(
            (sum(item[2] for item in line) + space_w * max(len(line) - 1, 0) for line in lines),
            default=0.0,
        )

        # --- Fallback: whole-segment scale & settle state ---
        fallback_scale = 1.0
        fallback_settled = True
        if (
            not use_word_timing
            and seg is not None
            and self.scale_from > 0.0
            and self.scale_duration_frac > 0.0
        ):
            seg_dur = seg.end - seg.start
            anim_dur = seg_dur * self.scale_duration_frac
            if anim_dur > 0.0:
                t_in = lyrics_t - seg.start
                if t_in < anim_dur:
                    fallback_scale = 1.0 + self.scale_from * (1.0 - ease_out(t_in / anim_dur))
                    fallback_settled = False

        # --- Paints ---
        r, g, bc, a = resolve_color(self.color, ctx.job.colors).rgba
        base_paint = skia.Paint(AntiAlias=True)
        base_paint.setColor4f(skia.Color4f(r, g, bc, a * self.opacity))

        hr, hg, hb, ha = resolve_color(self.highlight_color, ctx.job.colors).rgba
        hl_paint = skia.Paint(AntiAlias=True)
        hl_paint.setColor4f(skia.Color4f(hr, hg, hb, ha * self.opacity))

        if self.stroke_width > 0.0:
            skr, skg, skb, ska = resolve_color(self.stroke_color, ctx.job.colors).rgba
            stroke_paint = skia.Paint(AntiAlias=True)
            stroke_paint.setStyle(skia.Paint.kStroke_Style)
            stroke_paint.setStrokeWidth(spec.size * self.stroke_width)
            stroke_paint.setStrokeCap(skia.Paint.kRound_Cap)
            stroke_paint.setStrokeJoin(skia.Paint.kRound_Join)
            stroke_paint.setColor4f(skia.Color4f(skr, skg, skb, ska * self.opacity))
        else:
            stroke_paint = None

        canvas.save()
        canvas.clipRect(skia.Rect.MakeXYWH(b.x, b.y, b.width, b.height))

        # Fallback: apply whole-segment scale around actual text center
        if not use_word_timing and fallback_scale != 1.0:
            pivot_x = block_x + actual_w / 2.0
            canvas.translate(pivot_x, center_y)
            canvas.scale(fallback_scale, fallback_scale)
            canvas.translate(-pivot_x, -center_y)

        for line in lines:
            line_w = sum(item[2] for item in line) + space_w * max(len(line) - 1, 0)
            match self.align:
                case "left":
                    lx = block_x
                case "right":
                    lx = block_x + max_w - line_w
                case _:
                    lx = block_x + (max_w - line_w) / 2.0

            baseline = y - metrics.fAscent
            x = lx

            for i, (word_text, word_idx, word_w) in enumerate(line):
                if i > 0:
                    x += space_w

                if use_word_timing and word_idx is not None:
                    w = words[word_idx]
                    word_dur = w.end - w.start
                    anim_dur_word = max(word_dur * self.scale_duration_frac, self.min_word_anim)
                    t_word = lyrics_t - w.start

                    if t_word < 0.0:
                        # Not yet visible — hold space, skip draw
                        x += word_w
                        continue
                    elif t_word < anim_dur_word:
                        word_scale = 1.0 + self.scale_from * (
                            1.0 - ease_out(t_word / anim_dur_word)
                        )
                        fill_paint = base_paint
                    else:
                        word_scale = 1.0
                        fill_paint = hl_paint

                    pivot_x = x + word_w / 2.0
                    pivot_y = y + glyph_h / 2.0
                    canvas.save()
                    if word_scale != 1.0:
                        canvas.translate(pivot_x, pivot_y)
                        canvas.scale(word_scale, word_scale)
                        canvas.translate(-pivot_x, -pivot_y)
                    if stroke_paint is not None:
                        canvas.drawString(word_text, x, baseline, font, stroke_paint)
                    canvas.drawString(word_text, x, baseline, font, fill_paint)
                    canvas.restore()
                else:
                    fill_paint = hl_paint if fallback_settled else base_paint
                    if stroke_paint is not None:
                        canvas.drawString(word_text, x, baseline, font, stroke_paint)
                    canvas.drawString(word_text, x, baseline, font, fill_paint)

                x += word_w

            y += line_h

        canvas.restore()
