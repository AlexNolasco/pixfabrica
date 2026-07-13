from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import ClassVar, Literal

import skia
from pydantic import Field, PrivateAttr

from pixfabrica_core.clips import ClipCategory, ClipSkia, ClipTag, PrepareContext, RenderContext
from pixfabrica_core.graphics import Rect
from pixfabrica_core.lyrics import CaptionSegment, parse_lrc, parse_srt, parse_vtt, parse_whisperx
from pixfabrica_core.prepare_diagnostics import record_prepare_asset_failure
from pixfabrica_core.theme.color import Color, ColorToken, color_field, resolve_color
from pixfabrica_core.theme.typography import FontRole, FontSpec
from pixfabrica_std.text._text_utils import _case
from pixfabrica_std.text.skia_font import make_typography_font

log = logging.getLogger("pixfabrica.std.lyrics_caption")

# (text, original_word_index | None, advance_width)
_WordItem = tuple[str, int | None, float]


def _find_active(segments: list[CaptionSegment], t: float) -> CaptionSegment | None:
    lo, hi = 0, len(segments) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        seg = segments[mid]
        if t < seg.start:
            hi = mid - 1
        elif t >= seg.end:
            lo = mid + 1
        else:
            return seg
    return None


def _wrap(items: list[_WordItem], space_w: float, max_w: float) -> list[list[_WordItem]]:
    """Greedy word-wrap. A single word wider than max_w gets its own line."""
    lines: list[list[_WordItem]] = []
    current: list[_WordItem] = []
    current_w = 0.0
    for item in items:
        w = item[2]
        if not current:
            current.append(item)
            current_w = w
        elif current_w + space_w + w <= max_w:
            current.append(item)
            current_w += space_w + w
        else:
            lines.append(current)
            current = [item]
            current_w = w
    if current:
        lines.append(current)
    return lines


class LyricsCaption(ClipSkia):
    """Renders the active caption line each frame from LRC, SRT, VTT, or WhisperX JSON.

    Timing: lyrics_t = ctx.time.t - self.start + lyrics_offset.
    The clip's start field maps lyrics-time-zero to a job-timeline position.
    Between lines, shows placeholder (empty string = show nothing).
    """

    clip_type: ClassVar[str] = "std-lyrics-caption"
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
    highlight_bg: Color | ColorToken | None = Field(
        default=None, description="Background fill behind the highlighted word (None = off)"
    )
    highlight_bg_radius: float = Field(
        default=0.0,
        ge=0.0,
        le=0.5,
        multiple_of=0.01,
        description="Corner radius as fraction of glyph height (0 = sharp, 0.5 = full pill)",
    )
    highlight_mode: Literal["none", "word", "word_only"] = Field(
        default="word",
        description=(
            "'word' highlights the current word using word-level timestamps; "
            "'word_only' renders only the active word (placeholder shown between words, "
            "falls back to full line when word timestamps are absent); "
            "'none' draws all text in base color"
        ),
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

    async def prepare(self, ctx: PrepareContext, _bounds: Rect | None = None) -> None:
        import asyncio

        if not self.source:
            return
        key = (self.source,)
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
            log.warning("LyricsCaption %s: could not resolve %r — %s", self.id, self.source, exc)
            return
        try:
            self._segments = _parse(path)
            log.debug("LyricsCaption %s: loaded %d segments", self.id, len(self._segments))
        except Exception as exc:
            log.warning("LyricsCaption %s: parse failed — %s", self.id, exc)

    def draw(self, ctx: RenderContext) -> None:
        canvas: skia.Canvas = ctx.canvas
        b = ctx.bounds

        lyrics_t = ctx.time.t - self.start + self.lyrics_offset
        seg = _find_active(self._segments, lyrics_t) if self._segments else None

        text = _case(seg.text, self.text_case) if seg else self.placeholder
        if not text:
            return

        words = seg.words if seg else ()

        current_word_idx: int | None = None
        _force_hl = False

        if self.highlight_mode == "word_only":
            if words:
                for w in words:
                    if w.start <= lyrics_t < w.end:
                        text = _case(w.word, self.text_case)
                        words = ()
                        _force_hl = True
                        break
                else:
                    text = self.placeholder
                    words = ()
                if not text:
                    return
            # else: no word timestamps — fall through with full segment text
        elif self.highlight_mode == "word":
            for i, w in enumerate(words):
                if w.start <= lyrics_t < w.end:
                    current_word_idx = i
                    break

        spec: FontSpec = getattr(ctx.job.typography, self.typography_role)
        font = make_typography_font(spec)

        metrics = font.getMetrics()
        line_h = (-metrics.fAscent + metrics.fDescent) * spec.line_height
        space_w = font.measureText(" ")
        max_w = b.width * self.wrap_width

        # Build word items — use CaptionWord tokens when available for highlight tracking
        if words and self.highlight_mode == "word":
            items: list[_WordItem] = [
                (t := _case(w.word, self.text_case), i, font.measureText(t))
                for i, w in enumerate(words)
            ]
        else:
            items = [(tok, None, font.measureText(tok)) for tok in text.split()]

        lines = _wrap(items, space_w, max_w)
        total_h = len(lines) * line_h

        block_x = b.x + (b.width - max_w) * self.offset_x
        y = b.y + self.offset_y * b.height - total_h / 2.0

        # Paints
        r, g, bc, a = resolve_color(self.color, ctx.job.colors).rgba
        base_paint = skia.Paint(AntiAlias=True)
        base_paint.setColor4f(skia.Color4f(r, g, bc, a * self.opacity))

        hr, hg, hb, ha = resolve_color(self.highlight_color, ctx.job.colors).rgba
        hl_paint = skia.Paint(AntiAlias=True)
        hl_paint.setColor4f(skia.Color4f(hr, hg, hb, ha * self.opacity))

        bg_paint: skia.Paint | None = None
        if self.highlight_bg is not None:
            bgr, bgg, bgb, bga = resolve_color(self.highlight_bg, ctx.job.colors).rgba
            bg_paint = skia.Paint()
            bg_paint.setColor4f(skia.Color4f(bgr, bgg, bgb, bga))  # type: ignore[union-attr]

        glyph_h = -metrics.fAscent + metrics.fDescent

        canvas.save()
        canvas.clipRect(skia.Rect.MakeXYWH(b.x, b.y, b.width, b.height))

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

            for i, (word_text, word_idx, word_w) in enumerate(line):
                if i > 0:
                    x += space_w
                is_hl = _force_hl or (word_idx is not None and word_idx == current_word_idx)
                if is_hl and bg_paint is not None:
                    rect = skia.Rect.MakeXYWH(x, y, word_w, glyph_h)
                    r = self.highlight_bg_radius * glyph_h
                    if r > 0:
                        canvas.drawRoundRect(rect, r, r, bg_paint)
                    else:
                        canvas.drawRect(rect, bg_paint)
                canvas.drawString(word_text, x, baseline, font, hl_paint if is_hl else base_paint)
                x += word_w

            y += line_h

        canvas.restore()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse(path: Path) -> list[CaptionSegment]:
    content = path.read_text(encoding="utf-8", errors="replace")
    match path.suffix.lower():
        case ".lrc":
            return parse_lrc(content)
        case ".srt":
            return parse_srt(content)
        case ".vtt" | ".webvtt":
            return parse_vtt(content)
        case ".json":
            return parse_whisperx(content)
        case _:
            raise ValueError(f"Unsupported lyrics format: {path.suffix!r}")


def _resolve_source_sync(source: str, ctx: PrepareContext) -> Path:
    import httpx

    if source.startswith(("http://", "https://")):
        cache_dir = ctx.cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)
        url_hash = hashlib.sha256(source.encode()).hexdigest()
        ext = Path(source.split("?")[0]).suffix or ".lrc"
        cached = cache_dir / f"{url_hash}{ext}"
        if not cached.exists():
            tmp = cache_dir / f"{url_hash}.tmp"
            with httpx.Client() as client:
                response = client.get(source)
                response.raise_for_status()
                tmp.write_bytes(response.content)
            tmp.replace(cached)
        return cached

    return Path(source)
