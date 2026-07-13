from __future__ import annotations

import asyncio
import logging
import math
from typing import ClassVar

import skia
from pydantic import Field, PrivateAttr

from pixfabrica_core.clips import ClipCategory, ClipSkia, PrepareContext, RenderContext
from pixfabrica_core.graphics import Rect
from pixfabrica_core.theme.color import Color, ColorToken, color_field, resolve_color
from pixfabrica_core.theme.typography import FontRole
from pixfabrica_core.ui_schema import section_field
from pixfabrica_std.common import FitMode
from pixfabrica_std.player._card_layout import (
    THUMB_UPLOAD_POLICY,
    TextLineSpec,
    band_rect,
    draw_cover_thumb,
    draw_cover_thumb_top,
    draw_panel_background,
    draw_sidebar_text_cell,
    draw_text_cell,
    is_vertical_sidebar_zone,
    prepare_cover_image,
    sidebar_text_rotation_deg,
    thumb_max_px,
    vertical_sidebar_rect,
)
from pixfabrica_std.player.transport_icon import TransportState, draw_transport_icon
from pixfabrica_std.text.skia_font import make_typography_font
from pixfabrica_std.tilt import ANGLE_FULL_DESC, ANGLE_FULL_MAX, ANGLE_FULL_MIN

log = logging.getLogger("pixfabrica.std.track_card")

_PROGRESS_TRACK_ALPHA = 0.35


class TrackCard(ClipSkia):
    """Segment track card: cover art, title/author, transport glyph, and local progress strip."""

    clip_type: ClassVar[str] = "std-track-card"
    clip_category: ClassVar[ClipCategory] = ClipCategory.PLAYER
    clip_tags: ClassVar[list[str]] = []

    source: str | None = section_field(
        "cover",
        default=None,
        description="Cover art: local file path to a prepared image",
    )
    cover_scale: float = section_field(
        "cover",
        default=0.85,
        ge=0.2,
        le=1.0,
        multiple_of=0.01,
        description="Cover square side as a fraction of content row height",
    )
    fit: FitMode = section_field(
        "cover",
        default=FitMode.COVER,
        description="How non-square cover art fills the square thumb",
    )
    cover_fill: ColorToken | Color = section_field(
        "cover",
        default=ColorToken.BACKGROUND,
        description="Letterbox fill behind cover art when fit does not fill the square",
        json_schema_extra={"widget": "color"},
    )
    title: str = Field(default="{TITLE}", description="Primary line (track title)")
    author: str = Field(default="{AUTHOR}", description="Secondary line (artist / author)")
    title_typography_role: FontRole = Field(
        default="title_small",
        description="Typography role for the title line",
    )
    author_typography_role: FontRole = Field(
        default="body_small",
        description="Typography role for the author line",
    )
    title_color: ColorToken | Color = color_field(ColorToken.PRIMARY)
    author_color: ColorToken | Color = color_field(ColorToken.SECONDARY)
    transport_state: TransportState = Field(
        default="play",
        description="Transport glyph shown for the whole segment; none hides the icon",
    )
    transport_color: ColorToken | Color | None = Field(
        default=None,
        description="Transport glyph and ring color; defaults to title color when unset",
    )
    show_transport_circle: bool = Field(
        default=True,
        description="Draw a stroked circle around the transport glyph",
    )
    background: ColorToken | Color | None = Field(
        default=ColorToken.BACKGROUND,
        description="Panel fill color; unset for transparent background",
        json_schema_extra={"widget": "color"},
    )
    corner_radius: float = Field(
        default=0.025,
        ge=0.0,
        le=0.2,
        multiple_of=0.005,
        description="Panel and cover corner radius as a fraction of the shorter card axis",
    )
    progress_track: ColorToken | Color = color_field(ColorToken.NEUTRAL)
    progress_fill: ColorToken | Color = color_field(ColorToken.PRIMARY)
    progress_height: float = Field(
        default=0.03,
        ge=0.0,
        le=0.15,
        multiple_of=0.005,
        description="Progress strip height as a fraction of the card panel height (0 hides the strip)",
    )

    offset_x: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Card band center as fraction of clip bounds width (0=left, 1=right)",
    )
    offset_y: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Card band center as fraction of clip bounds height (0=top, 1=bottom)",
    )
    width: float = Field(
        default=1.0,
        ge=0.01,
        le=1.0,
        multiple_of=0.01,
        description="Card width as fraction of clip bounds width (1=full width)",
    )
    band_height: float = Field(
        default=0.12,
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
    opacity: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Overall layer opacity",
    )
    content_inset_x: float = Field(
        default=0.05,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Horizontal inset from content row edges for cover art (left) and transport (right), as fraction of content width",
    )
    transport_scale: float = Field(
        default=0.5,
        ge=0.1,
        le=1.0,
        multiple_of=0.01,
        description="Transport icon diameter as a fraction of content row height",
    )

    text_gap: float = Field(
        default=0.03,
        ge=0.0,
        le=0.3,
        multiple_of=0.01,
        description="Gap between cover, text column, and transport as a fraction of content width",
    )

    _cover_image: skia.Image | None = PrivateAttr(default=None)

    @classmethod
    def source_upload_policy(cls):
        return THUMB_UPLOAD_POLICY

    @classmethod
    def source_max_px(
        cls,
        bounds: Rect,
        *,
        cover_scale: float,
        progress_height: float,
        band_height: float,
    ) -> int:
        return thumb_max_px(
            bounds,
            padding_x=0.0,
            padding_y=0.0,
            cover_scale=cover_scale,
            progress_height=progress_height,
            band_height=band_height,
        )

    async def prepare(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        await asyncio.to_thread(self._prepare_sync, ctx, bounds)

    def _prepare_sync(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        b = bounds or Rect(0, 0, ctx.job.width, ctx.job.height)
        max_dim = self.source_max_px(
            b,
            cover_scale=self.cover_scale,
            progress_height=self.progress_height,
            band_height=self.band_height,
        )
        self._cover_image = prepare_cover_image(
            source=self.source,
            ctx=ctx,
            bounds=bounds,
            clip_type=self.clip_type,
            clip_id=self.id,
            fit=self.fit,
            max_dim=max_dim,
            log=log,
        )

    def _target_band_width(self, bounds: Rect) -> float:
        return min(float(bounds.width), max(1.0, float(self.width) * float(bounds.width)))

    def _resolve_card_rect(self, ctx: RenderContext) -> Rect:
        bounds = ctx.bounds
        if is_vertical_sidebar_zone(self.angle):
            return vertical_sidebar_rect(
                bounds,
                offset_x=self.offset_x,
                offset_y=self.offset_y,
                thickness_frac=self.band_height,
                span_frac=self.width,
            )
        target_bw = self._target_band_width(bounds)
        if self.angle == 0.0:
            return band_rect(
                bounds,
                offset_x=self.offset_x,
                offset_y=self.offset_y,
                band_height=self.band_height,
                band_width=target_bw,
            )
        abs_rad = abs(math.radians(self.angle))
        cos_a = math.cos(abs_rad)
        sin_a = math.sin(abs_rad)
        card_h = max(0.01, min(1.0, self.band_height)) * bounds.height
        needed_w = (bounds.width - card_h * sin_a) / cos_a if cos_a > 1e-6 else bounds.width
        band_width = max(target_bw, needed_w)
        return band_rect(
            bounds,
            offset_x=self.offset_x,
            offset_y=self.offset_y,
            band_height=self.band_height,
            band_width=band_width,
        )

    def _panel_and_content_row(self, card: Rect) -> tuple[Rect, Rect]:
        panel = card
        progress_h = float(panel.height) * self.progress_height
        content = Rect(
            float(panel.x),
            float(panel.y) + progress_h,
            float(panel.width),
            float(panel.height) - progress_h,
        )
        return panel, content

    def _measure_content_band_width(self, ctx: RenderContext, bounds: Rect) -> float:
        """Intrinsic band width for tilted cards (avoids a full-bleed diagonal slash)."""
        bh = max(0.01, min(1.0, float(self.band_height))) * bounds.height
        min_w = max(bh * 1.75, 48.0)
        title_font = make_typography_font(getattr(ctx.job.typography, self.title_typography_role))
        author_font = make_typography_font(getattr(ctx.job.typography, self.author_typography_role))
        text_w = max(
            title_font.measureText(self.title),
            author_font.measureText(self.author) if self.author else 0.0,
        )

        target_bw = self._target_band_width(bounds)
        band_w = min(float(bounds.width), max(min_w, bh * 4.0, target_bw))
        for _ in range(6):
            card = band_rect(
                bounds,
                offset_x=self.offset_x,
                offset_y=self.offset_y,
                band_height=self.band_height,
                band_width=max(band_w, target_bw),
            )
            _, content = self._panel_and_content_row(card)
            gap_px = self.text_gap * content.width
            inset_px = self.content_inset_x * content.width
            cover_side = (
                min(content.height * self.cover_scale, content.height)
                if self._cover_image is not None
                else 0.0
            )
            transport_d = (
                0.0
                if self.transport_state == "none"
                else min(content.height * self.transport_scale, content.height)
            )
            thumb_inset = inset_px if cover_side > 0 else 0.0
            text_left = content.x + thumb_inset + cover_side + (gap_px if cover_side > 0 else 0.0)
            if self.transport_state == "none":
                avail = content.width - (text_left - content.x) - gap_px
            else:
                transport_cx = content.x + content.width - inset_px - transport_d / 2.0
                avail = max(0.0, transport_cx - transport_d / 2.0 - gap_px - text_left)
            if avail + 0.5 >= text_w:
                return min(float(bounds.width), max(min_w, band_w))
            band_w = min(float(bounds.width), band_w * 1.2 + 24.0)
        return float(bounds.width)

    def _draw_vertical_sidebar(self, ctx: RenderContext) -> None:
        canvas: skia.Canvas = ctx.canvas
        b = ctx.bounds
        panel = self._resolve_card_rect(ctx)

        canvas.save()
        canvas.clipRect(skia.Rect.MakeXYWH(float(b.x), float(b.y), float(b.width), float(b.height)))

        layer_active = self.opacity < 1.0
        if layer_active:
            layer_paint = skia.Paint()
            layer_paint.setAlphaf(self.opacity)
            canvas.saveLayer(
                skia.Rect.MakeXYWH(float(b.x), float(b.y), float(b.width), float(b.height)),
                layer_paint,
            )

        if self.background is not None:
            draw_panel_background(
                canvas,
                panel,
                background=self.background,
                corner_radius=self.corner_radius,
                colors=ctx.job.colors,
            )

        progress_w = float(panel.width) * self.progress_height
        span = self.duration if self.duration is not None else ctx.job.duration
        local_t = max(0.0, ctx.time.t - self.start)
        progress = min(local_t / max(span, 1e-6), 1.0)

        if progress_w > 0:
            track = resolve_color(self.progress_track, ctx.job.colors)
            tr, tg, tb, ta = track.rgba
            track_paint = skia.Paint(AntiAlias=True)
            track_paint.setColor4f(skia.Color4f(tr, tg, tb, ta * _PROGRESS_TRACK_ALPHA))
            canvas.drawRect(
                skia.Rect.MakeXYWH(float(panel.x), float(panel.y), progress_w, float(panel.height)),
                track_paint,
            )
            if progress > 0:
                fill_c = resolve_color(self.progress_fill, ctx.job.colors)
                fr, fg, fb, fa = fill_c.rgba
                fill_paint = skia.Paint(AntiAlias=True)
                fill_paint.setColor4f(skia.Color4f(fr, fg, fb, fa))
                canvas.drawRect(
                    skia.Rect.MakeXYWH(
                        float(panel.x),
                        float(panel.y),
                        progress_w,
                        float(panel.height) * progress,
                    ),
                    fill_paint,
                )

        content = Rect(
            float(panel.x) + progress_w,
            float(panel.y),
            float(panel.width) - progress_w,
            float(panel.height),
        )

        gap_px = self.text_gap * content.height
        inset_px = self.content_inset_x * content.height
        transport_d = min(content.width * self.transport_scale, content.width)

        cover_bottom = draw_cover_thumb_top(
            canvas,
            content,
            self._cover_image,
            cover_scale=self.cover_scale,
            fit=self.fit,
            cover_fill=self.cover_fill,
            corner_radius=self.corner_radius,
            colors=ctx.job.colors,
            content_inset=self.content_inset_x,
        )

        transport_top = content.y + content.height - inset_px - transport_d
        text_top = cover_bottom + (gap_px if self._cover_image is not None else 0.0)
        text_bottom = (
            transport_top - gap_px
            if self.transport_state != "none"
            else content.y + content.height - inset_px
        )
        text_extent = max(0.0, text_bottom - text_top)

        if text_extent > 0:
            draw_sidebar_text_cell(
                canvas,
                pivot_x=content.x + content.width / 2.0,
                pivot_y=text_top + text_extent / 2.0,
                text_span=text_extent,
                cross_span=content.width,
                rotation_deg=sidebar_text_rotation_deg(self.angle),
                lines=[
                    TextLineSpec(self.title, self.title_typography_role, self.title_color),
                    TextLineSpec(self.author, self.author_typography_role, self.author_color),
                ],
                typography=ctx.job.typography,
                colors=ctx.job.colors,
            )

        transport_color = resolve_color(
            self.transport_color if self.transport_color is not None else self.title_color,
            ctx.job.colors,
        )
        if self.transport_state != "none":
            draw_transport_icon(
                canvas,
                center_x=content.x + content.width / 2.0,
                center_y=transport_top + transport_d / 2.0,
                diameter=transport_d,
                state=self.transport_state,
                color=transport_color,
                show_circle=self.show_transport_circle,
            )

        if layer_active:
            canvas.restore()
        canvas.restore()

    def draw(self, ctx: RenderContext) -> None:
        if is_vertical_sidebar_zone(self.angle):
            self._draw_vertical_sidebar(ctx)
            return

        canvas: skia.Canvas = ctx.canvas
        b = ctx.bounds
        card = self._resolve_card_rect(ctx)

        canvas.save()
        canvas.clipRect(skia.Rect.MakeXYWH(float(b.x), float(b.y), float(b.width), float(b.height)))

        layer_active = self.opacity < 1.0
        if layer_active:
            layer_paint = skia.Paint()
            layer_paint.setAlphaf(self.opacity)
            canvas.saveLayer(
                skia.Rect.MakeXYWH(float(b.x), float(b.y), float(b.width), float(b.height)),
                layer_paint,
            )

        pivot_x = card.x + card.width / 2.0
        pivot_y = card.y + card.height / 2.0
        canvas.translate(pivot_x, pivot_y)
        if self.angle:
            canvas.rotate(self.angle)

        local_card = Rect(-card.width / 2.0, -card.height / 2.0, card.width, card.height)
        panel = local_card

        visible_w = min(card.width, ctx.bounds.width)
        local_content_card = Rect(-visible_w / 2.0, -card.height / 2.0, visible_w, card.height)
        content_panel = local_content_card

        if self.background is not None:
            draw_panel_background(
                canvas,
                panel,
                background=self.background,
                corner_radius=self.corner_radius,
                colors=ctx.job.colors,
            )

        progress_h = float(panel.height) * self.progress_height
        span = self.duration if self.duration is not None else ctx.job.duration
        local_t = max(0.0, ctx.time.t - self.start)
        progress = min(local_t / max(span, 1e-6), 1.0)

        if progress_h > 0:
            track = resolve_color(self.progress_track, ctx.job.colors)
            tr, tg, tb, ta = track.rgba
            track_paint = skia.Paint(AntiAlias=True)
            track_paint.setColor4f(skia.Color4f(tr, tg, tb, ta * _PROGRESS_TRACK_ALPHA))
            canvas.drawRect(
                skia.Rect.MakeXYWH(float(panel.x), float(panel.y), float(panel.width), progress_h),
                track_paint,
            )

            if progress > 0:
                fill_c = resolve_color(self.progress_fill, ctx.job.colors)
                fr, fg, fb, fa = fill_c.rgba
                fill_paint = skia.Paint(AntiAlias=True)
                fill_paint.setColor4f(skia.Color4f(fr, fg, fb, fa))
                canvas.drawRect(
                    skia.Rect.MakeXYWH(
                        float(panel.x), float(panel.y), float(panel.width) * progress, progress_h
                    ),
                    fill_paint,
                )

        content = Rect(
            float(content_panel.x),
            float(content_panel.y) + progress_h,
            float(content_panel.width),
            float(content_panel.height) - progress_h,
        )

        gap_px = self.text_gap * content.width
        inset_px = self.content_inset_x * content.width
        transport_d = min(content.height * self.transport_scale, content.height)
        transport_cx = content.x + content.width - inset_px - transport_d / 2.0
        transport_left = transport_cx - transport_d / 2.0

        cover_right = draw_cover_thumb(
            canvas,
            content,
            self._cover_image,
            cover_scale=self.cover_scale,
            fit=self.fit,
            cover_fill=self.cover_fill,
            corner_radius=self.corner_radius,
            colors=ctx.job.colors,
            content_inset_x=self.content_inset_x,
        )

        text_left = cover_right + (gap_px if self._cover_image is not None else 0.0)
        if self.transport_state == "none":
            text_right = content.x + content.width - gap_px
        else:
            text_right = transport_left - gap_px
        text_width = max(0.0, text_right - text_left)

        draw_text_cell(
            canvas,
            content,
            lines=[
                TextLineSpec(self.title, self.title_typography_role, self.title_color),
                TextLineSpec(self.author, self.author_typography_role, self.author_color),
            ],
            text_left=text_left,
            text_width=text_width,
            typography=ctx.job.typography,
            colors=ctx.job.colors,
        )

        transport_color = resolve_color(
            self.transport_color if self.transport_color is not None else self.title_color,
            ctx.job.colors,
        )
        if self.transport_state != "none":
            draw_transport_icon(
                canvas,
                center_x=transport_cx,
                center_y=content.y + content.height / 2.0,
                diameter=transport_d,
                state=self.transport_state,
                color=transport_color,
                show_circle=self.show_transport_circle,
            )

        if layer_active:
            canvas.restore()
        canvas.restore()
