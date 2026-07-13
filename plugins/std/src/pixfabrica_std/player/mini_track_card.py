from __future__ import annotations

import asyncio
import logging
import math
from typing import ClassVar

import skia
from pydantic import Field, PrivateAttr

from pixfabrica_core.clips import ClipCategory, ClipSkia, PrepareContext, RenderContext
from pixfabrica_core.graphics import Rect
from pixfabrica_core.theme.color import Color, ColorToken, color_field
from pixfabrica_std.player._card_layout import (
    MINI_AUTHOR_ROLE,
    MINI_CORNER_RADIUS,
    MINI_COVER_SCALE,
    MINI_FIT,
    MINI_PADDING_X,
    MINI_PADDING_Y,
    MINI_TEXT_GAP,
    MINI_TITLE_ROLE,
    THUMB_UPLOAD_POLICY,
    TextLineSpec,
    band_rect,
    card_rect,
    content_rect,
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
from pixfabrica_std.text.skia_font import make_typography_font
from pixfabrica_std.tilt import ANGLE_FULL_DESC, ANGLE_FULL_MAX, ANGLE_FULL_MIN

log = logging.getLogger("pixfabrica.std.mini_track_card")


class MiniTrackCard(ClipSkia):
    """Compact track strip: cover thumb, title/author, and panel background only."""

    clip_type: ClassVar[str] = "std-mini-track-card"
    clip_category: ClassVar[ClipCategory] = ClipCategory.PLAYER
    clip_tags: ClassVar[list[str]] = []

    source: str | None = Field(
        default=None,
        description="Cover art: local file path to a prepared image",
    )
    title: str = Field(default="{TITLE}", description="Primary line (track title)")
    author: str = Field(default="{AUTHOR}", description="Secondary line (artist / author)")
    title_color: ColorToken | Color = color_field(ColorToken.PRIMARY)
    author_color: ColorToken | Color = color_field(ColorToken.SECONDARY)
    background: ColorToken | Color = color_field(ColorToken.BACKGROUND)
    offset_x: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Card band center as fraction of clip bounds width (0=left, 1=right)",
    )
    offset_y: float = Field(
        default=0.9,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Card band center as fraction of clip bounds height (0=top, 1=bottom)",
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

    _cover_image: skia.Image | None = PrivateAttr(default=None)

    @classmethod
    def source_upload_policy(cls):
        return THUMB_UPLOAD_POLICY

    async def prepare(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        await asyncio.to_thread(self._prepare_sync, ctx, bounds)

    def _prepare_sync(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        b = bounds or Rect(0, 0, ctx.job.width, ctx.job.height)
        max_dim = thumb_max_px(
            b,
            padding_x=MINI_PADDING_X,
            padding_y=MINI_PADDING_Y,
            cover_scale=MINI_COVER_SCALE,
            band_height=self.band_height,
            progress_height=0.0,
        )
        self._cover_image = prepare_cover_image(
            source=self.source,
            ctx=ctx,
            bounds=bounds,
            clip_type=self.clip_type,
            clip_id=self.id,
            fit=MINI_FIT,
            max_dim=max_dim,
            log=log,
        )

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
        title_font = make_typography_font(getattr(ctx.job.typography, MINI_TITLE_ROLE))
        author_font = make_typography_font(getattr(ctx.job.typography, MINI_AUTHOR_ROLE))
        text_w = max(
            title_font.measureText(self.title),
            author_font.measureText(self.author) if self.author else 0.0,
        )

        band_w = min(float(bounds.width), max(min_w, bh * 4.0))
        for _ in range(6):
            card = band_rect(
                bounds,
                offset_x=self.offset_x,
                offset_y=self.offset_y,
                band_height=self.band_height,
                band_width=band_w,
            )
            content = content_rect(card, 0.0, MINI_PADDING_Y)
            gap_px = MINI_TEXT_GAP * content.width
            cover_side = (
                min(content.height * MINI_COVER_SCALE, content.height)
                if self._cover_image is not None
                else 0.0
            )
            if self._cover_image is None:
                avail = content.width - gap_px
            else:
                text_left = content.x + gap_px + cover_side + gap_px
                avail = (content.x + content.width - gap_px) - text_left
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

        draw_panel_background(
            canvas,
            panel,
            background=self.background,
            corner_radius=MINI_CORNER_RADIUS,
            colors=ctx.job.colors,
        )

        content = panel
        gap_px = MINI_TEXT_GAP * content.height
        pad_px = MINI_PADDING_Y * content.height

        cover_bottom = draw_cover_thumb_top(
            canvas,
            content,
            self._cover_image,
            cover_scale=MINI_COVER_SCALE,
            fit=MINI_FIT,
            cover_fill=ColorToken.BACKGROUND,
            corner_radius=MINI_CORNER_RADIUS,
            colors=ctx.job.colors,
            content_inset=MINI_TEXT_GAP,
        )

        text_top = cover_bottom + (gap_px if self._cover_image is not None else pad_px)
        text_bottom = content.y + content.height - pad_px
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
                    TextLineSpec(self.title, MINI_TITLE_ROLE, self.title_color),
                    TextLineSpec(self.author, MINI_AUTHOR_ROLE, self.author_color),
                ],
                typography=ctx.job.typography,
                colors=ctx.job.colors,
            )

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

        pivot_x = card.x + card.width / 2.0
        pivot_y = card.y + card.height / 2.0
        canvas.translate(pivot_x, pivot_y)
        if self.angle:
            canvas.rotate(self.angle)

        local_card = Rect(-card.width / 2.0, -card.height / 2.0, card.width, card.height)
        panel = local_card
        visible_w = min(card.width, ctx.bounds.width)
        local_content_card = Rect(-visible_w / 2.0, -card.height / 2.0, visible_w, card.height)
        content = content_rect(local_content_card, 0.0, MINI_PADDING_Y)

        draw_panel_background(
            canvas,
            panel,
            background=self.background,
            corner_radius=MINI_CORNER_RADIUS,
            colors=ctx.job.colors,
        )

        gap_px = MINI_TEXT_GAP * content.width
        if self._cover_image is not None:
            cover_area = Rect(
                content.x + gap_px,
                content.y,
                max(0.0, content.width - gap_px),
                content.height,
            )
            cover_right = draw_cover_thumb(
                canvas,
                cover_area,
                self._cover_image,
                cover_scale=MINI_COVER_SCALE,
                fit=MINI_FIT,
                cover_fill=ColorToken.BACKGROUND,
                corner_radius=MINI_CORNER_RADIUS,
                colors=ctx.job.colors,
            )
            text_left = cover_right + gap_px
        else:
            text_left = content.x
        text_width = max(0.0, content.x + content.width - gap_px - text_left)

        draw_text_cell(
            canvas,
            content,
            lines=[
                TextLineSpec(self.title, MINI_TITLE_ROLE, self.title_color),
                TextLineSpec(self.author, MINI_AUTHOR_ROLE, self.author_color),
            ],
            text_left=text_left,
            text_width=text_width,
            typography=ctx.job.typography,
            colors=ctx.job.colors,
        )

        canvas.restore()
