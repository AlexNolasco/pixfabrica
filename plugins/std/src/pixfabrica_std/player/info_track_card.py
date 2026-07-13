from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import ClassVar

import skia
from pydantic import Field

from pixfabrica_core.clips import ClipCategory, ClipSkia, PrepareContext, RenderContext
from pixfabrica_core.graphics import Rect
from pixfabrica_core.theme.color import Color, ColorPalette, ColorToken, color_field, resolve_color
from pixfabrica_core.theme.typography import FontRole
from pixfabrica_std.player._card_layout import (
    band_rect,
    card_rect,
    content_rect,
    draw_panel_background,
    ellipsize,
    is_vertical_sidebar_zone,
    sidebar_text_rotation_deg,
    vertical_sidebar_rect,
    wrap_text_lines,
)
from pixfabrica_std.player._info_format import (
    format_duration,
    format_grouped_count,
    format_medium_date,
    format_play_count,
    resolve_info_date,
)
from pixfabrica_std.player._player_svg import RowIconName, draw_row_icon
from pixfabrica_std.player.transport_icon import TransportState, draw_transport_icon
from pixfabrica_std.text.skia_font import make_typography_font
from pixfabrica_std.tilt import ANGLE_FULL_DESC, ANGLE_FULL_MAX, ANGLE_FULL_MIN

log = logging.getLogger("pixfabrica.std.info_track_card")

INFO_PADDING = 0.03
INFO_CORNER_RADIUS = 0.0
INFO_COL_GAP = 0.03
INFO_ROW_GAP = 0.05
INFO_ICON_TEXT_GAP = 0.35
INFO_CHIP_GAP = 0.05
INFO_META_SEP = " · "
INFO_TITLE_ROLE: FontRole = "title_medium"
INFO_AUTHOR_ROLE: FontRole = "body_medium"
INFO_DETAIL_ROLE: FontRole = "body_small"


@dataclass(frozen=True, slots=True)
class _IconSegment:
    icon: RowIconName | None
    text: str


class InfoTrackCard(ClipSkia):
    """Metadata track card: title/author, transport, plays/duration/date, and social stats."""

    clip_type: ClassVar[str] = "std-info-track-card"
    clip_category: ClassVar[ClipCategory] = ClipCategory.PLAYER
    clip_tags: ClassVar[list[str]] = []

    title: str = Field(default="{TITLE}", description="Primary line (track title)")
    author: str = Field(default="{AUTHOR}", description="Secondary line (artist / author)")
    play_count: int = Field(
        default=199_000, ge=0, le=500_000, multiple_of=100, description="Total play count"
    )
    date: str | None = Field(
        default=None,
        description="Release or publish date (ISO YYYY-MM-DD); unset uses render day",
    )
    likes: int = Field(default=1245, ge=0, le=500_000, multiple_of=100, description="Like count")
    comments: int = Field(
        default=87, ge=0, le=500_000, multiple_of=100, description="Comment count"
    )
    replays: int = Field(default=312, ge=0, le=500_000, multiple_of=100, description="Replay count")
    transport_state: TransportState = Field(
        default="play",
        description="Transport glyph beside title/author; none hides the icon",
    )
    title_color: ColorToken | Color = color_field(ColorToken.PRIMARY)
    author_color: ColorToken | Color = color_field(ColorToken.SECONDARY)
    meta_color: ColorToken | Color = color_field(ColorToken.NEUTRAL_VARIANT)
    stats_color: ColorToken | Color = color_field(ColorToken.SECONDARY)
    background: ColorToken | Color | None = Field(
        default=ColorToken.BACKGROUND,
        description="Panel fill color; unset for transparent background",
        json_schema_extra={"widget": "color"},
    )
    offset_x: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Card band center as fraction of clip bounds width (0=left, 1=right)",
    )
    offset_y: float = Field(
        default=0.88,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Card band center as fraction of clip bounds height (0=top, 1=bottom)",
    )
    band_height: float = Field(
        default=0.26,
        ge=0.01,
        le=1.0,
        multiple_of=0.01,
        description="Card band thickness as fraction of clip bounds height (1=full height)",
    )
    angle: float = Field(
        default=0.0,
        ge=ANGLE_FULL_MIN,
        le=ANGLE_FULL_MAX,
        multiple_of=1.0,
        description=ANGLE_FULL_DESC,
    )

    async def prepare(self, _ctx: PrepareContext, _bounds: Rect | None = None) -> None:
        pass

    def _resolve_card_rect(self, ctx: RenderContext) -> Rect:
        bounds = ctx.bounds
        if is_vertical_sidebar_zone(self.angle):
            return vertical_sidebar_rect(
                bounds,
                offset_x=self.offset_x,
                offset_y=self.offset_y,
                thickness_frac=self.band_height,
                span_frac=1.0,
            )
        if self.angle == 0.0:
            return card_rect(
                bounds,
                offset_x=self.offset_x,
                offset_y=self.offset_y,
                band_height=self.band_height,
            )
        abs_rad = abs(math.radians(self.angle))
        cos_a = math.cos(abs_rad)
        sin_a = math.sin(abs_rad)
        card_h = max(0.01, min(1.0, self.band_height)) * bounds.height
        needed_w = (bounds.width - card_h * sin_a) / cos_a if cos_a > 1e-6 else bounds.width
        band_width = max(bounds.width, needed_w)
        return band_rect(
            bounds,
            offset_x=self.offset_x,
            offset_y=self.offset_y,
            band_height=self.band_height,
            band_width=band_width,
        )

    def _measure_content_band_width(self, ctx: RenderContext, bounds: Rect) -> float:
        """Intrinsic band width for tilted cards (avoids a full-bleed diagonal slash)."""
        bh = max(0.01, min(1.0, float(self.band_height))) * bounds.height
        min_w = max(bh * 1.75, 48.0)
        probe = band_rect(
            bounds,
            offset_x=self.offset_x,
            offset_y=self.offset_y,
            band_height=self.band_height,
            band_width=min(bounds.width, max(min_w, bh * 4.0)),
        )
        content = content_rect(probe, INFO_PADDING, INFO_PADDING)
        title_font = make_typography_font(getattr(ctx.job.typography, INFO_TITLE_ROLE))
        author_font = make_typography_font(getattr(ctx.job.typography, INFO_AUTHOR_ROLE))
        detail_font = make_typography_font(getattr(ctx.job.typography, INFO_DETAIL_ROLE))

        edge_pad = _edge_pad(content)
        transport_d_est = _estimate_transport_diameter(title_font, author_font, detail_font)
        transport_reserve = (
            edge_pad + transport_d_est + edge_pad if self.transport_state != "none" else 0.0
        )
        text_width = max(0.0, content.width - transport_reserve)

        title_lines = wrap_text_lines(self.title, title_font, text_width, max_lines=2)
        title_w = max((title_font.measureText(line) for line in title_lines), default=0.0)
        author_w = author_font.measureText(self.author) if self.author else 0.0
        header_text_w = max(title_w, author_w)
        header_w = header_text_w + (transport_reserve if self.transport_state != "none" else 0.0)

        locale = ctx.job.locale
        span = self.duration if self.duration is not None else ctx.job.duration
        meta_w = _measure_icon_row_width(
            detail_font,
            segments=self._meta_segments(locale, span_sec=span),
            separator=INFO_META_SEP,
        )
        stats_w = _measure_icon_row_width(
            detail_font,
            segments=self._stat_segments(locale),
            chip_gap=INFO_CHIP_GAP * content.width,
        )

        inner_w = max(header_w, meta_w, stats_w)
        pad = INFO_PADDING * probe.width * 2.0
        return min(float(bounds.width), max(min_w, inner_w + pad))

    def _draw_info_content_rows(
        self,
        canvas: skia.Canvas,
        ctx: RenderContext,
        content: Rect,
        *,
        include_transport: bool,
    ) -> None:
        """Paragraph rows: title, author, optional inline transport, meta, stats."""
        edge_pad = _edge_pad(content)
        text_left = content.x

        title_font = make_typography_font(getattr(ctx.job.typography, INFO_TITLE_ROLE))
        author_font = make_typography_font(getattr(ctx.job.typography, INFO_AUTHOR_ROLE))
        detail_font = make_typography_font(getattr(ctx.job.typography, INFO_DETAIL_ROLE))

        transport_d_est = _estimate_transport_diameter(title_font, author_font, detail_font)
        transport_reserve = (
            edge_pad + transport_d_est + edge_pad
            if include_transport and self.transport_state != "none"
            else 0.0
        )
        text_width = max(0.0, content.width - transport_reserve)

        title_lines = wrap_text_lines(self.title, title_font, text_width, max_lines=2)
        title_metrics = title_font.getMetrics()
        title_line_h = -title_metrics.fAscent + title_metrics.fDescent
        title_gap = max(2.0, title_line_h * 0.12) if len(title_lines) > 1 else 0.0
        title_block_h = (
            len(title_lines) * title_line_h + title_gap * max(0, len(title_lines) - 1)
            if title_lines
            else 0.0
        )

        author_text = ellipsize(self.author, author_font, text_width) if self.author else ""
        author_metrics = author_font.getMetrics()
        author_line_h = -author_metrics.fAscent + author_metrics.fDescent
        header_text_gap = max(2.0, title_line_h * 0.14) if title_lines and author_text else 0.0
        text_block_h = title_block_h + header_text_gap + (author_line_h if author_text else 0.0)

        transport_d = 0.0
        if include_transport and self.transport_state != "none":
            transport_d = max(text_block_h * 0.85, detail_font.getSize() * 2.4)
        header_block_h = max(text_block_h, transport_d if transport_d else 0.0)
        if header_block_h <= 0.0:
            header_block_h = detail_font.getSize() * 2.0

        title_paint = _text_paint(self.title_color, ctx.job.colors)
        y = content.y
        for idx, line in enumerate(title_lines):
            baseline = y - title_metrics.fAscent
            canvas.drawString(line, text_left, baseline, title_font, title_paint)
            y += title_line_h + (title_gap if idx + 1 < len(title_lines) else 0.0)

        if author_text:
            if title_lines:
                y += header_text_gap
            author_paint = _text_paint(self.author_color, ctx.job.colors)
            author_baseline = y - author_metrics.fAscent
            canvas.drawString(author_text, text_left, author_baseline, author_font, author_paint)

        if include_transport and self.transport_state != "none" and transport_d > 0:
            button_color = resolve_color(self.title_color, ctx.job.colors)
            glyph_bg = self.background if self.background is not None else ColorToken.BACKGROUND
            glyph_color = resolve_color(glyph_bg, ctx.job.colors)
            icon_cx = content.x + content.width - edge_pad - transport_d / 2.0
            draw_transport_icon(
                canvas,
                center_x=icon_cx,
                center_y=content.y + header_block_h / 2.0,
                diameter=transport_d,
                state=self.transport_state,
                color=button_color,
                show_circle=False,
                circle_fill=True,
                glyph_color=glyph_color,
                glyph_scale=1.0,
            )

        header_extent = header_block_h if include_transport else text_block_h
        y_cursor = content.y + header_extent + INFO_ROW_GAP * content.height
        locale = ctx.job.locale
        span = self.duration if self.duration is not None else ctx.job.duration

        row_width = (
            text_width + transport_reserve
            if include_transport and self.transport_state != "none"
            else content.width
        )

        meta_segments = self._meta_segments(locale, span_sec=span)
        if meta_segments:
            meta_paint = _text_paint(self.meta_color, ctx.job.colors)
            row_h = _draw_icon_row(
                canvas,
                x=text_left,
                y_top=y_cursor,
                width=row_width,
                font=detail_font,
                paint=meta_paint,
                color=resolve_color(self.meta_color, ctx.job.colors),
                segments=meta_segments,
                separator=INFO_META_SEP,
            )
            y_cursor += row_h + INFO_ROW_GAP * content.height

        stat_segments = self._stat_segments(locale)
        if stat_segments:
            stats_paint = _text_paint(self.stats_color, ctx.job.colors)
            _draw_icon_row(
                canvas,
                x=text_left,
                y_top=y_cursor,
                width=row_width,
                font=detail_font,
                paint=stats_paint,
                color=resolve_color(self.stats_color, ctx.job.colors),
                segments=stat_segments,
                chip_gap=INFO_CHIP_GAP * content.width,
            )

    def _draw_vertical_sidebar(self, ctx: RenderContext) -> None:
        canvas: skia.Canvas = ctx.canvas
        bounds = ctx.bounds
        panel = self._resolve_card_rect(ctx)

        canvas.save()
        canvas.clipRect(
            skia.Rect.MakeXYWH(
                float(bounds.x),
                float(bounds.y),
                float(bounds.width),
                float(bounds.height),
            )
        )

        if self.background is not None:
            draw_panel_background(
                canvas,
                panel,
                background=self.background,
                corner_radius=INFO_CORNER_RADIUS,
                colors=ctx.job.colors,
            )

        content = content_rect(panel, INFO_PADDING, INFO_PADDING)
        gap_px = INFO_COL_GAP * content.height
        row_gap = INFO_ROW_GAP * content.height

        title_font = make_typography_font(getattr(ctx.job.typography, INFO_TITLE_ROLE))
        author_font = make_typography_font(getattr(ctx.job.typography, INFO_AUTHOR_ROLE))
        detail_font = make_typography_font(getattr(ctx.job.typography, INFO_DETAIL_ROLE))
        title_metrics = title_font.getMetrics()
        title_line_h = -title_metrics.fAscent + title_metrics.fDescent
        author_metrics = author_font.getMetrics()
        author_line_h = -author_metrics.fAscent + author_metrics.fDescent
        text_block_h = title_line_h * 2.0 + author_line_h

        transport_d = 0.0
        if self.transport_state != "none":
            transport_d = min(
                content.width * 0.85,
                max(text_block_h * 0.85, detail_font.getSize() * 2.4),
            )

        content_bottom = content.y + content.height
        if transport_d > 0:
            transport_top = content_bottom - gap_px - transport_d
            text_span = transport_top - row_gap - content.y
        else:
            transport_top = 0.0
            text_span = content.height

        canvas.save()
        canvas.translate(content.x + content.width / 2.0, content.y + text_span / 2.0)
        canvas.rotate(sidebar_text_rotation_deg(self.angle))
        virtual = Rect(-text_span / 2.0, -content.width / 2.0, text_span, content.width)
        self._draw_info_content_rows(canvas, ctx, virtual, include_transport=False)
        canvas.restore()

        if transport_d > 0:
            button_color = resolve_color(self.title_color, ctx.job.colors)
            glyph_bg = self.background if self.background is not None else ColorToken.BACKGROUND
            glyph_color = resolve_color(glyph_bg, ctx.job.colors)
            pivot_x = content.x + content.width / 2.0
            draw_transport_icon(
                canvas,
                center_x=pivot_x,
                center_y=transport_top + transport_d / 2.0,
                diameter=transport_d,
                state=self.transport_state,
                color=button_color,
                show_circle=False,
                circle_fill=True,
                glyph_color=glyph_color,
                glyph_scale=1.0,
            )

        canvas.restore()

    def draw(self, ctx: RenderContext) -> None:
        if is_vertical_sidebar_zone(self.angle):
            self._draw_vertical_sidebar(ctx)
            return

        canvas: skia.Canvas = ctx.canvas
        bounds = ctx.bounds
        card = self._resolve_card_rect(ctx)

        canvas.save()
        canvas.clipRect(
            skia.Rect.MakeXYWH(
                float(bounds.x),
                float(bounds.y),
                float(bounds.width),
                float(bounds.height),
            )
        )

        pivot_x = card.x + card.width / 2.0
        pivot_y = card.y + card.height / 2.0
        canvas.translate(pivot_x, pivot_y)
        if self.angle:
            canvas.rotate(self.angle)

        local_card = Rect(-card.width / 2.0, -card.height / 2.0, card.width, card.height)
        visible_w = min(card.width, ctx.bounds.width)
        local_content_card = Rect(-visible_w / 2.0, -card.height / 2.0, visible_w, card.height)
        content = content_rect(local_content_card, INFO_PADDING, INFO_PADDING)

        if self.background is not None:
            draw_panel_background(
                canvas,
                local_card,
                background=self.background,
                corner_radius=INFO_CORNER_RADIUS,
                colors=ctx.job.colors,
            )

        self._draw_info_content_rows(canvas, ctx, content, include_transport=True)

        canvas.restore()

    def _meta_segments(self, locale: str, *, span_sec: float) -> list[_IconSegment]:
        segments: list[_IconSegment] = []
        if self.play_count > 0:
            segments.append(
                _IconSegment("play", format_play_count(self.play_count, locale)),
            )
        if span_sec > 0:
            segments.append(_IconSegment(None, format_duration(span_sec)))
        segments.append(
            _IconSegment(None, format_medium_date(resolve_info_date(self.date), locale)),
        )
        return segments

    def _stat_segments(self, locale: str) -> list[_IconSegment]:
        segments: list[_IconSegment] = []
        if self.likes > 0:
            segments.append(_IconSegment("heart", format_grouped_count(self.likes, locale)))
        if self.comments > 0:
            segments.append(
                _IconSegment("message-circle", format_grouped_count(self.comments, locale))
            )
        if self.replays > 0:
            segments.append(_IconSegment("repeat", format_grouped_count(self.replays, locale)))
        return segments


def _edge_pad(content: Rect) -> float:
    """Horizontal inset from content edges; caps width-scaled gap on wide landscape bands."""
    return min(INFO_COL_GAP * content.width, INFO_COL_GAP * content.height)


def _estimate_transport_diameter(
    title_font: skia.Font,
    author_font: skia.Font,
    detail_font: skia.Font,
) -> float:
    title_metrics = title_font.getMetrics()
    title_line_h = -title_metrics.fAscent + title_metrics.fDescent
    author_metrics = author_font.getMetrics()
    author_line_h = -author_metrics.fAscent + author_metrics.fDescent
    header_h_est = title_line_h * 2.0 + author_line_h
    return max(header_h_est * 0.85, detail_font.getSize() * 2.4)


def _measure_icon_row_width(
    font: skia.Font,
    *,
    segments: list[_IconSegment],
    separator: str = "",
    chip_gap: float = 0.0,
) -> float:
    if not segments:
        return 0.0
    metrics = font.getMetrics()
    line_h = -metrics.fAscent + metrics.fDescent
    icon_size = line_h * 0.88
    icon_text_gap = icon_size * INFO_ICON_TEXT_GAP
    width = 0.0
    for idx, segment in enumerate(segments):
        if idx > 0:
            if separator:
                width += font.measureText(separator)
            elif chip_gap > 0:
                width += chip_gap
        if segment.icon is not None:
            width += icon_size + icon_text_gap
        width += font.measureText(segment.text)
    return width


def _text_paint(token: ColorToken | Color, colors: ColorPalette) -> skia.Paint:
    color = resolve_color(token, colors)
    r, g, b, a = color.rgba
    paint = skia.Paint(AntiAlias=True)
    paint.setColor4f(skia.Color4f(r, g, b, a))
    return paint


def _draw_icon_row(
    canvas: skia.Canvas,
    *,
    x: float,
    y_top: float,
    width: float,
    font: skia.Font,
    paint: skia.Paint,
    color: Color,
    segments: list[_IconSegment],
    separator: str = "",
    chip_gap: float = 0.0,
) -> float:
    metrics = font.getMetrics()
    line_h = -metrics.fAscent + metrics.fDescent
    icon_size = line_h * 0.88
    icon_text_gap = icon_size * INFO_ICON_TEXT_GAP
    baseline = y_top - metrics.fAscent
    text_center_y = y_top + line_h / 2.0
    icon_y = text_center_y - icon_size / 2.0
    cursor = x
    max_x = x + width

    for idx, segment in enumerate(segments):
        if idx > 0:
            if separator:
                sep_w = font.measureText(separator)
                if cursor + sep_w > max_x:
                    break
                canvas.drawString(separator, cursor, baseline, font, paint)
                cursor += sep_w
            elif chip_gap > 0:
                cursor += chip_gap

        if segment.icon is not None:
            if cursor + icon_size + icon_text_gap > max_x:
                break
            draw_row_icon(
                canvas,
                name=segment.icon,
                x=cursor,
                y=icon_y,
                size=icon_size,
                color=color,
            )
            cursor += icon_size + icon_text_gap

        text_w = font.measureText(segment.text)
        if cursor + text_w > max_x:
            clipped = ellipsize(segment.text, font, max(0.0, max_x - cursor))
            if clipped:
                canvas.drawString(clipped, cursor, baseline, font, paint)
            break
        canvas.drawString(segment.text, cursor, baseline, font, paint)
        cursor += text_w

    return line_h
