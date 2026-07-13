from __future__ import annotations

import zlib
from typing import ClassVar, Literal

import skia
from pydantic import Field

from pixfabrica_core.clips import ClipCategory, ClipSkia, ClipTag, PrepareContext, RenderContext
from pixfabrica_core.easing import ease_out
from pixfabrica_core.graphics import Rect
from pixfabrica_core.theme.color import Color, ColorToken, color_field, resolve_color
from pixfabrica_core.theme.typography import FontRole, FontSpec
from pixfabrica_std.text.skia_font import make_typography_font
from pixfabrica_std.tilt import ANGLE_FULL_DESC, ANGLE_FULL_MAX, ANGLE_FULL_MIN

_SCRAMBLE_CHARSET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789#$%&@*+=?"
_SCRAMBLE_REROLL_FRAMES = 3  # unresolved glyphs reroll every N frames
_CURSOR_BLINK_PERIOD = 0.5  # seconds per blink cycle after typing completes
_CURSOR_LINGER = 1.0  # seconds the cursor keeps blinking after typing completes
_CASCADE_RISE_EM = 0.5  # vertical travel of each word during cascade entry
_SETTLE_FRACTION = 0.3  # fraction of the clip duration spent animating (spread/cascade)
_SETTLE_CAP = 1.5  # seconds — long clips still get a snappy entry


class DynamicText(ClipSkia):
    """Text with a one-shot entry animation that plays once and holds.

    Effects:
      - spread: letters ease apart from normal spacing to an extra tracking distance.
      - typewriter: characters reveal at a constant rate with an optional cursor.
      - scramble: random glyphs resolve left-to-right into the real text.
      - cascade: words fade in and rise into place in reading order.

    All effects run on clip-local time (t - start) and hold their final state.
    Spread and cascade settle within the first 30% of the clip duration,
    capped at 1.5 s; typewriter and scramble are paced by type_speed instead.
    """

    clip_type: ClassVar[str] = "std-dynamic-text"
    clip_category: ClassVar[ClipCategory] = ClipCategory.TEXT
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED]

    text: str = Field(default="{TITLE}", description="Text content to render")
    effect: Literal["spread", "typewriter", "scramble", "cascade"] = Field(
        default="spread", description="Entry animation effect"
    )
    typography_role: FontRole = Field(
        default="body_medium", description="Typography role from the job theme"
    )
    color: ColorToken | Color = color_field(ColorToken.NEUTRAL)
    offset_x: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Horizontal anchor as fraction of bounds width (0=left, 1=right)",
    )
    offset_y: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Vertical anchor as fraction of bounds height (0=top, 1=bottom)",
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
    spread: float = Field(
        default=0.5,
        ge=0.0,
        le=4.0,
        multiple_of=0.1,
        description="Extra gap added between letters in em units (spread effect)",
    )
    type_speed: float = Field(
        default=12.0,
        ge=1.0,
        le=60.0,
        multiple_of=1.0,
        description="Characters per second (typewriter and scramble effects)",
    )
    cursor: bool = Field(
        default=True,
        description="Show a typing cursor that blinks briefly after typing completes (typewriter)",
    )
    align: Literal["left", "center", "right"] = Field(
        default="center", description="Text alignment relative to the offset_x anchor"
    )

    async def prepare(self, _ctx: PrepareContext, _bounds: Rect | None = None) -> None:
        pass

    def _settle_time(self) -> float:
        """Seconds until spread/cascade settle, derived from the clip duration."""
        if self.duration is None:
            return _SETTLE_CAP
        return max(min(_SETTLE_FRACTION * self.duration, _SETTLE_CAP), 1e-3)

    def _line_x(self, x_anchor: float, line_width: float) -> float:
        match self.align:
            case "left":
                return x_anchor
            case "right":
                return x_anchor - line_width
            case _:
                return x_anchor - line_width / 2.0

    def draw(self, ctx: RenderContext) -> None:
        if not self.text:
            return
        canvas: skia.Canvas = ctx.canvas
        b = ctx.bounds

        spec: FontSpec = getattr(ctx.job.typography, self.typography_role)
        font = make_typography_font(spec)
        font.setLinearMetrics(True)

        metrics = font.getMetrics()
        lines = self.text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        line_height = -metrics.fAscent + metrics.fDescent

        x_anchor = b.x + self.offset_x * b.width
        y_anchor = b.y + self.offset_y * b.height
        first_baseline = y_anchor - (len(lines) * line_height) / 2.0 - metrics.fAscent

        r, g, bl, a = resolve_color(self.color, ctx.job.colors).rgba
        paint = skia.Paint(AntiAlias=True)
        paint.setColor4f(skia.Color4f(r, g, bl, a * self.opacity))

        local_t = max(0.0, ctx.time.t - self.start)

        canvas.save()
        canvas.clipRect(skia.Rect.MakeXYWH(b.x, b.y, b.width, b.height))
        if self.angle:
            canvas.rotate(self.angle, x_anchor, y_anchor)

        match self.effect:
            case "typewriter":
                self._draw_typewriter(
                    canvas, font, paint, lines, x_anchor, first_baseline, line_height, local_t
                )
            case "scramble":
                self._draw_scramble(
                    canvas,
                    font,
                    paint,
                    lines,
                    x_anchor,
                    first_baseline,
                    line_height,
                    local_t,
                    ctx.time.frame,
                )
            case "cascade":
                self._draw_cascade(
                    canvas,
                    font,
                    paint,
                    lines,
                    x_anchor,
                    first_baseline,
                    line_height,
                    local_t,
                    base_alpha=a * self.opacity,
                    rgb=(r, g, bl),
                )
            case _:
                self._draw_spread(
                    canvas, font, paint, lines, x_anchor, first_baseline, line_height, local_t
                )

        canvas.restore()

    # ------------------------------------------------------------------ spread

    def _draw_spread(
        self,
        canvas: skia.Canvas,
        font: skia.Font,
        paint: skia.Paint,
        lines: list[str],
        x_anchor: float,
        first_baseline: float,
        line_height: float,
        local_t: float,
    ) -> None:
        progress = ease_out(min(local_t / self._settle_time(), 1.0))
        extra_gap = progress * self.spread * font.getSize()

        # Letters draw individually so tracking can animate; kerning is lost,
        # which is invisible once any extra gap is applied.
        for i, line in enumerate(lines):
            if not line:
                continue
            widths = [font.measureText(ch) for ch in line]
            line_width = sum(widths) + extra_gap * (len(line) - 1)
            x = self._line_x(x_anchor, line_width)
            baseline = first_baseline + i * line_height
            for ch, width in zip(line, widths, strict=True):
                if not ch.isspace():
                    canvas.drawString(ch, x, baseline, font, paint)
                x += width + extra_gap

    # -------------------------------------------------------------- typewriter

    def _draw_typewriter(
        self,
        canvas: skia.Canvas,
        font: skia.Font,
        paint: skia.Paint,
        lines: list[str],
        x_anchor: float,
        first_baseline: float,
        line_height: float,
        local_t: float,
    ) -> None:
        total_chars = sum(len(line) for line in lines)
        revealed = min(int(local_t * self.type_speed), total_chars)

        # Lines are laid out at their final position; characters appear in place.
        consumed = 0
        cursor_pos: tuple[float, float] | None = None
        for i, line in enumerate(lines):
            baseline = first_baseline + i * line_height
            line_x = self._line_x(x_anchor, font.measureText(line))
            n = max(0, min(len(line), revealed - consumed))
            prefix = line[:n]
            if prefix:
                canvas.drawString(prefix, line_x, baseline, font, paint)
            if consumed <= revealed <= consumed + len(line):
                cursor_pos = (line_x + font.measureText(prefix), baseline)
            consumed += len(line)

        if self.cursor and cursor_pos is not None:
            done_t = total_chars / self.type_speed
            if revealed < total_chars:
                visible = True
            else:
                since_done = local_t - done_t
                visible = (
                    since_done <= _CURSOR_LINGER
                    and (since_done % _CURSOR_BLINK_PERIOD) < _CURSOR_BLINK_PERIOD / 2.0
                )
            if visible:
                metrics = font.getMetrics()
                size = font.getSize()
                cx, cy = cursor_pos
                canvas.drawRect(
                    skia.Rect.MakeXYWH(
                        cx, cy + metrics.fAscent, size * 0.1, -metrics.fAscent + metrics.fDescent
                    ),
                    paint,
                )

    # ---------------------------------------------------------------- scramble

    def _draw_scramble(
        self,
        canvas: skia.Canvas,
        font: skia.Font,
        paint: skia.Paint,
        lines: list[str],
        x_anchor: float,
        first_baseline: float,
        line_height: float,
        local_t: float,
        frame: int,
    ) -> None:
        total_chars = sum(len(line) for line in lines)
        resolved = min(int(local_t * self.type_speed), total_chars)
        reroll = frame // _SCRAMBLE_REROLL_FRAMES

        # All glyphs draw at the final text's per-char positions so the layout
        # never jitters as unresolved glyphs reroll.
        consumed = 0
        for i, line in enumerate(lines):
            baseline = first_baseline + i * line_height
            x = self._line_x(x_anchor, font.measureText(line))
            for j, ch in enumerate(line):
                width = font.measureText(ch)
                if not ch.isspace():
                    if consumed + j < resolved:
                        glyph = ch
                    else:
                        # Deterministic across processes: hash() is salted per
                        # interpreter, which would desync parallel workers.
                        seed = zlib.crc32(f"{self.id}:{reroll}:{consumed + j}".encode())
                        glyph = _SCRAMBLE_CHARSET[seed % len(_SCRAMBLE_CHARSET)]
                    canvas.drawString(glyph, x, baseline, font, paint)
                x += width
            consumed += len(line)

    # ----------------------------------------------------------------- cascade

    def _draw_cascade(
        self,
        canvas: skia.Canvas,
        font: skia.Font,
        paint: skia.Paint,
        lines: list[str],
        x_anchor: float,
        first_baseline: float,
        line_height: float,
        local_t: float,
        *,
        base_alpha: float,
        rgb: tuple[float, float, float],
    ) -> None:
        word_count = sum(len(line.split()) for line in lines)
        if word_count == 0:
            return
        # Word i animates over [i * stagger, (i + 2) * stagger]; the last word
        # settles exactly at the settle time.
        stagger = self._settle_time() / (word_count + 1)
        word_dur = 2.0 * stagger
        rise = _CASCADE_RISE_EM * font.getSize()
        space_w = font.measureText(" ")
        r, g, bl = rgb

        index = 0
        for i, line in enumerate(lines):
            words = line.split()
            if not words:
                continue
            widths = [font.measureText(w) for w in words]
            line_width = sum(widths) + space_w * (len(words) - 1)
            x = self._line_x(x_anchor, line_width)
            baseline = first_baseline + i * line_height
            for word, width in zip(words, widths, strict=True):
                progress = ease_out(min(max((local_t - index * stagger) / word_dur, 0.0), 1.0))
                if progress > 0.0:
                    paint.setColor4f(skia.Color4f(r, g, bl, base_alpha * progress))
                    canvas.drawString(word, x, baseline + (1.0 - progress) * rise, font, paint)
                x += width + space_w
                index += 1
