"""Shared layout, cover prepare, and draw helpers for player track cards."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import skia
from PIL import Image as PILImage

from pixfabrica_core.clips import PrepareContext
from pixfabrica_core.file_upload_policy import ContentThumbFactorPolicy, manifest_covers_max_px
from pixfabrica_core.graphics import Rect
from pixfabrica_core.prepare_diagnostics import record_prepare_asset_failure
from pixfabrica_core.theme.color import Color, ColorPalette, ColorToken, resolve_color
from pixfabrica_core.theme.typography import FontPalette, FontRole, FontSpec
from pixfabrica_std.common import FitMode
from pixfabrica_std.image.background_image import _draw_fitted
from pixfabrica_std.media_source import resolve_local_source_path
from pixfabrica_std.text.skia_font import make_typography_font

THUMB_UPLOAD_POLICY = ContentThumbFactorPolicy(factor=2.0, thumb_max_px=512.0)

# Baked defaults for std-mini-track-card (and reference values for full card defaults).
MINI_COVER_SCALE = 0.85
MINI_CORNER_RADIUS = 0.025
MINI_PADDING_X = 0.0
MINI_PADDING_Y = 0.05
MINI_TEXT_GAP = 0.03
MINI_TITLE_ROLE: FontRole = "title_small"
MINI_AUTHOR_ROLE: FontRole = "body_small"
MINI_FIT = FitMode.COVER


def content_rect(bounds: Rect, padding_x: float, padding_y: float) -> Rect:
    px = max(0.0, min(0.9, float(padding_x)))
    py = max(0.0, min(0.9, float(padding_y)))
    iw = bounds.width * (1.0 - px)
    ih = bounds.height * (1.0 - py)
    ix = bounds.x + bounds.width * px * 0.5
    iy = bounds.y + bounds.height * py * 0.5
    return Rect(ix, iy, iw, ih)


def card_rect(
    bounds: Rect,
    *,
    offset_x: float,
    offset_y: float,
    band_height: float,
) -> Rect:
    """Card band: full clip width, ``band_height`` × bounds height, anchored at offsets."""
    bh = max(0.01, min(1.0, float(band_height))) * bounds.height
    bw = bounds.width
    cx = bounds.x + float(offset_x) * bounds.width
    cy = bounds.y + float(offset_y) * bounds.height
    return Rect(cx - bw / 2.0, cy - bh / 2.0, bw, bh)


def band_rect(
    bounds: Rect,
    *,
    offset_x: float,
    offset_y: float,
    band_height: float,
    band_width: float,
) -> Rect:
    """Card band with explicit width, centered on offsets (for tilted content-fit layout)."""
    bh = max(0.01, min(1.0, float(band_height))) * bounds.height
    bw = min(float(bounds.width), max(1.0, float(band_width)))
    cx = bounds.x + float(offset_x) * bounds.width
    cy = bounds.y + float(offset_y) * bounds.height
    return Rect(cx - bw / 2.0, cy - bh / 2.0, bw, bh)


VERTICAL_SIDEBAR_MIN_DEG = 75.0
VERTICAL_SIDEBAR_MAX_DEG = 105.0


def normalized_perpendicular_angle(angle: float) -> float:
    """Map angle to acute measure relative to horizontal (0° or 180° → 0)."""
    a = abs(float(angle)) % 180.0
    if a > 90.0:
        a = 180.0 - a
    return a


def is_vertical_sidebar_zone(angle: float) -> bool:
    """True when the card uses native vertical column layout (≈ ±90°)."""
    a = normalized_perpendicular_angle(angle)
    return VERTICAL_SIDEBAR_MIN_DEG <= a <= VERTICAL_SIDEBAR_MAX_DEG


def vertical_sidebar_rect(
    bounds: Rect,
    *,
    offset_x: float,
    offset_y: float,
    thickness_frac: float,
    span_frac: float,
) -> Rect:
    """Vertical sidebar: thin axis = ``thickness_frac`` × bounds height, long = ``span_frac`` × bounds height."""
    thickness = max(1.0, max(0.01, min(1.0, float(thickness_frac))) * float(bounds.height))
    span = max(
        1.0, min(float(bounds.height), max(0.01, min(1.0, float(span_frac))) * float(bounds.height))
    )
    cx = bounds.x + float(offset_x) * bounds.width
    cy = bounds.y + float(offset_y) * bounds.height
    return Rect(cx - thickness / 2.0, cy - span / 2.0, thickness, span)


def sidebar_text_rotation_deg(angle: float) -> float:
    """Rotate label text to run along a vertical sidebar long axis."""
    return -90.0 if float(angle) >= 0.0 else 90.0


def draw_cover_thumb_top(
    canvas: skia.Canvas,
    content: Rect,
    cover_image: skia.Image | None,
    *,
    cover_scale: float,
    fit: FitMode,
    cover_fill: ColorToken | Color,
    corner_radius: float,
    colors: ColorPalette,
    content_inset: float = 0.0,
) -> float:
    """Draw square cover anchored to the top of a vertical column; return y after cover."""
    cover_side = min(content.width * cover_scale, content.width)
    inset_px = max(0.0, min(0.9, float(content_inset))) * content.height
    cover_x = content.x + (content.width - cover_side) / 2.0
    cover_y = content.y + (inset_px if cover_image is not None and cover_side > 0 else 0.0)
    if cover_image is None or cover_side <= 0:
        return cover_y

    radius = panel_corner_radius(content, corner_radius)
    cover_rect = skia.RRect()
    cover_radius = min(radius, cover_side * 0.12)
    cover_rect.setRectXY(
        skia.Rect.MakeXYWH(cover_x, cover_y, cover_side, cover_side),
        cover_radius,
        cover_radius,
    )
    canvas.save()
    canvas.clipRRect(cover_rect, skia.ClipOp.kIntersect, True)
    if fit != FitMode.COVER:
        fill_c = resolve_color(cover_fill, colors)
        cr, cg, cb, ca = fill_c.rgba
        cover_bg = skia.Paint(AntiAlias=True)
        cover_bg.setColor4f(skia.Color4f(cr, cg, cb, ca))
        canvas.drawRect(skia.Rect.MakeXYWH(cover_x, cover_y, cover_side, cover_side), cover_bg)
    image_paint = skia.Paint(AntiAlias=True)
    _draw_fitted(
        canvas,
        Rect(cover_x, cover_y, cover_side, cover_side),
        cover_image,
        FitMode.COVER if fit == FitMode.COVER else fit,
        image_paint,
    )
    canvas.restore()
    return cover_y + cover_side


def draw_sidebar_rotated_text(
    canvas: skia.Canvas,
    *,
    pivot_x: float,
    slot_top: float,
    slot_extent: float,
    rotation_deg: float,
    max_extent: float,
    lines: list[TextLineSpec],
    typography: FontPalette,
    colors: ColorPalette,
    slot_align: str = "start",
    column_gap: float = 0.0,
    layout: str = "columns",
) -> float:
    """Draw rotated label text along the sidebar long axis.

    ``columns``: title and author as parallel vertical columns (track card).
    ``stack``: title then author stacked along the axis (info card).
    Returns the block extent consumed along the long axis (0 when nothing drawn).
    """
    rendered: list[tuple[str, skia.Font, skia.Paint, float, float]] = []
    for spec in lines:
        if not spec.text:
            continue
        role_spec: FontSpec = getattr(typography, spec.typography_role)
        font = make_typography_font(role_spec)
        metrics = font.getMetrics()
        line_h = -metrics.fAscent + metrics.fDescent
        c = resolve_color(spec.color, colors)
        r, g, b, a = c.rgba
        paint = skia.Paint(AntiAlias=True)
        paint.setColor4f(skia.Color4f(r, g, b, a))
        text = ellipsize(spec.text, font, max_extent)
        line_w = font.measureText(text)
        rendered.append((text, font, paint, line_h, line_w))

    if not rendered:
        return 0.0

    gap = max(2.0, float(column_gap))

    if layout == "stack":
        max_ascent = max(-font.getMetrics().fAscent for _, font, _, _, _ in rendered)
        max_descent = max(font.getMetrics().fDescent for _, font, _, _, _ in rendered)
        baseline_y = (max_ascent - max_descent) / 2.0
        block_w = sum(line_w for _, _, _, _, line_w in rendered) + gap * max(0, len(rendered) - 1)
        if max_extent > 0 and block_w > max_extent:
            budget = max_extent
            trimmed: list[tuple[str, skia.Font, skia.Paint, float, float]] = []
            for idx, (text, font, paint, line_h, line_w) in enumerate(rendered):
                if budget <= 0:
                    break
                sep = gap if idx + 1 < len(rendered) else 0.0
                if line_w + sep > budget and idx == len(rendered) - 1:
                    trimmed.append((ellipsize(text, font, budget), font, paint, line_h, budget))
                    budget = 0.0
                    break
                trimmed.append((text, font, paint, line_h, line_w))
                budget -= line_w + sep
            rendered = trimmed
            block_w = sum(line_w for _, _, _, _, line_w in rendered) + gap * max(
                0, len(rendered) - 1
            )
        if block_w <= 0:
            return 0.0

        pivot_y = (
            slot_top + slot_extent / 2.0 if slot_align == "center" else slot_top + block_w / 2.0
        )
        canvas.save()
        canvas.translate(pivot_x, pivot_y)
        canvas.rotate(rotation_deg)
        if rotation_deg < 0.0:
            x = block_w / 2.0
            for idx, (text, font, paint, _line_h, line_w) in enumerate(rendered):
                if text:
                    x -= line_w
                    canvas.drawString(text, x, baseline_y, font, paint)
                    x -= gap if idx + 1 < len(rendered) else 0.0
        else:
            x = -block_w / 2.0
            for idx, (text, font, paint, _line_h, line_w) in enumerate(rendered):
                if text:
                    canvas.drawString(text, x, baseline_y, font, paint)
                    x += line_w + (gap if idx + 1 < len(rendered) else 0.0)
        canvas.restore()
        return block_w

    cross_sizes = [line_h for _, _, _, line_h, _ in rendered]
    total_cross = sum(cross_sizes) + gap * max(0, len(rendered) - 1)
    max_w = max(line_w for _, _, _, _, line_w in rendered)

    col_y = -total_cross / 2.0
    columns: list[tuple[str, skia.Font, skia.Paint, float, float]] = []
    for text, font, paint, line_h, line_w in rendered:
        col_center_y = col_y + line_h / 2.0
        col_y += line_h + gap
        columns.append((text, font, paint, line_w, col_center_y))

    pivot_y = slot_top + slot_extent / 2.0 if slot_align == "center" else slot_top + max_w / 2.0

    canvas.save()
    canvas.translate(pivot_x, pivot_y)
    canvas.rotate(rotation_deg)
    for text, font, paint, line_w, col_center_y in columns:
        metrics = font.getMetrics()
        ascent = -metrics.fAscent
        baseline_y = col_center_y + (metrics.fDescent - ascent) / 2.0
        x = max_w / 2.0 - line_w if rotation_deg < 0.0 else -max_w / 2.0
        canvas.drawString(text, x, baseline_y, font, paint)
    canvas.restore()
    return max_w


def draw_sidebar_text_cell(
    canvas: skia.Canvas,
    *,
    pivot_x: float,
    pivot_y: float,
    text_span: float,
    cross_span: float,
    rotation_deg: float,
    lines: list[TextLineSpec],
    typography: FontPalette,
    colors: ColorPalette,
) -> None:
    """Draw stacked title/author rows in a virtual horizontal band, rotated along the sidebar."""
    if text_span <= 0 or cross_span <= 0 or not lines:
        return

    canvas.save()
    canvas.translate(pivot_x, pivot_y)
    canvas.rotate(rotation_deg)
    virtual = Rect(-text_span / 2.0, -cross_span / 2.0, text_span, cross_span)
    draw_text_cell(
        canvas,
        virtual,
        lines=lines,
        text_left=virtual.x,
        text_width=virtual.width,
        typography=typography,
        colors=colors,
    )
    canvas.restore()


def card_pivot(bounds: Rect, offset_x: float, offset_y: float) -> tuple[float, float]:
    """Rotation pivot at the card band anchor (same center as ``card_rect``)."""
    return (
        float(bounds.x) + float(offset_x) * float(bounds.width),
        float(bounds.y) + float(offset_y) * float(bounds.height),
    )


def rotate_canvas_for_card(
    canvas: skia.Canvas,
    bounds: Rect,
    *,
    angle: float,
    offset_x: float,
    offset_y: float,
) -> None:
    if angle:
        px, py = card_pivot(bounds, offset_x, offset_y)
        canvas.rotate(angle, px, py)


def ellipsize(text: str, font: skia.Font, max_width: float, ellipsis: str = "...") -> str:
    if not text or max_width <= 0:
        return ""
    if font.measureText(text) <= max_width:
        return text
    ell_w = font.measureText(ellipsis)
    if ell_w > max_width:
        return ""
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if font.measureText(text[:mid]) + ell_w <= max_width:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo] + ellipsis if lo > 0 else ellipsis


def crop_square_center(pil_img: PILImage.Image) -> PILImage.Image:
    w, h = pil_img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    return pil_img.crop((left, top, left + side, top + side))


def thumb_max_px(
    bounds: Rect,
    *,
    padding_x: float,
    padding_y: float,
    cover_scale: float,
    band_height: float,
    progress_height: float = 0.0,
) -> int:
    return THUMB_UPLOAD_POLICY.max_px_from_bounds(
        bounds.width,
        bounds.height,
        padding_x=padding_x,
        padding_y=padding_y,
        cover_scale=cover_scale,
        progress_height=progress_height,
        band_height=band_height,
    )


def prepare_cover_image(
    *,
    source: str | None,
    ctx: PrepareContext,
    bounds: Rect | None,
    clip_type: str,
    clip_id: str,
    fit: FitMode,
    max_dim: int,
    log: logging.Logger,
) -> skia.Image | None:
    if not source:
        return None

    try:
        local_path = resolve_local_source_path(source)
    except Exception as exc:
        record_prepare_asset_failure(
            ctx,
            kind="clip",
            ref_id=clip_id,
            clip_type=clip_type,
            field="source",
            source=source,
            exc=exc,
        )
        log.warning("%s %s: could not resolve source %r — %s", clip_type, clip_id, source, exc)
        return None

    if not local_path.is_file():
        record_prepare_asset_failure(
            ctx,
            kind="clip",
            ref_id=clip_id,
            clip_type=clip_type,
            field="source",
            source=source,
            exc=FileNotFoundError(local_path),
            code="not_found",
        )
        log.warning("%s %s: source file not found %r", clip_type, clip_id, local_path)
        return None

    try:
        pil_img = PILImage.open(str(local_path)).convert("RGBA")
    except Exception as exc:
        record_prepare_asset_failure(
            ctx,
            kind="clip",
            ref_id=clip_id,
            clip_type=clip_type,
            field="source",
            source=source,
            exc=exc,
            code="load_failed",
        )
        log.warning("%s %s: failed to load image %r — %s", clip_type, clip_id, local_path, exc)
        return None

    if fit == FitMode.COVER:
        pil_img = crop_square_center(pil_img)

    if (
        not manifest_covers_max_px(local_path, max_dim)
        and max(pil_img.width, pil_img.height) > max_dim
    ):
        pil_img.thumbnail((max_dim, max_dim), PILImage.Resampling.LANCZOS)

    return skia.Image.fromarray(
        np.array(pil_img),
        colorType=skia.ColorType.kRGBA_8888_ColorType,
    )


def panel_corner_radius(panel: Rect, corner_radius: float) -> float:
    short_axis = min(float(panel.width), float(panel.height))
    return corner_radius * short_axis


def draw_panel_background(
    canvas: skia.Canvas,
    panel: Rect,
    *,
    background: ColorToken | Color,
    corner_radius: float,
    colors: ColorPalette,
) -> skia.RRect:
    radius = panel_corner_radius(panel, corner_radius)
    outer = skia.RRect()
    outer.setRectXY(
        skia.Rect.MakeXYWH(float(panel.x), float(panel.y), float(panel.width), float(panel.height)),
        radius,
        radius,
    )
    bg = resolve_color(background, colors)
    br, bg_g, bb, ba = bg.rgba
    fill = skia.Paint(AntiAlias=True)
    fill.setColor4f(skia.Color4f(br, bg_g, bb, ba))
    canvas.drawRRect(outer, fill)
    return outer


def draw_cover_thumb(
    canvas: skia.Canvas,
    content: Rect,
    cover_image: skia.Image | None,
    *,
    cover_scale: float,
    fit: FitMode,
    cover_fill: ColorToken | Color,
    corner_radius: float,
    colors: ColorPalette,
    content_inset_x: float = 0.0,
) -> float:
    """Draw square cover; return x position after cover (or content.x when no image)."""
    cover_side = min(content.height * cover_scale, content.height)
    inset_px = max(0.0, min(0.9, float(content_inset_x))) * content.width
    cover_x = content.x + (inset_px if cover_image is not None and cover_side > 0 else 0.0)
    cover_y = content.y + (content.height - cover_side) / 2.0
    if cover_image is None or cover_side <= 0:
        return cover_x

    radius = panel_corner_radius(content, corner_radius)
    cover_rect = skia.RRect()
    cover_radius = min(radius, cover_side * 0.12)
    cover_rect.setRectXY(
        skia.Rect.MakeXYWH(cover_x, cover_y, cover_side, cover_side),
        cover_radius,
        cover_radius,
    )
    canvas.save()
    canvas.clipRRect(cover_rect, skia.ClipOp.kIntersect, True)
    if fit != FitMode.COVER:
        fill_c = resolve_color(cover_fill, colors)
        cr, cg, cb, ca = fill_c.rgba
        cover_bg = skia.Paint(AntiAlias=True)
        cover_bg.setColor4f(skia.Color4f(cr, cg, cb, ca))
        canvas.drawRect(skia.Rect.MakeXYWH(cover_x, cover_y, cover_side, cover_side), cover_bg)
    image_paint = skia.Paint(AntiAlias=True)
    _draw_fitted(
        canvas,
        Rect(cover_x, cover_y, cover_side, cover_side),
        cover_image,
        FitMode.COVER if fit == FitMode.COVER else fit,
        image_paint,
    )
    canvas.restore()
    return cover_x + cover_side


def wrap_text_lines(
    text: str,
    font: skia.Font,
    max_width: float,
    max_lines: int = 2,
    ellipsis: str = "...",
) -> list[str]:
    """Word-wrap ``text`` to at most ``max_lines``; ellipsize the last line when needed."""
    if not text or max_width <= 0 or max_lines <= 0:
        return []

    words = text.split()
    if not words:
        return []

    lines: list[str] = []
    index = 0
    while index < len(words) and len(lines) < max_lines:
        line = ""
        while index < len(words):
            word = words[index]
            candidate = word if not line else f"{line} {word}"
            if font.measureText(candidate) <= max_width:
                line = candidate
                index += 1
            else:
                break

        if line:
            if index < len(words) and len(lines) == max_lines - 1:
                remainder = " ".join([line, *words[index:]])
                lines.append(ellipsize(remainder, font, max_width, ellipsis))
                return lines
            lines.append(line)
            continue

        word = words[index]
        if len(lines) == max_lines - 1:
            remainder = " ".join(words[index:])
            lines.append(ellipsize(remainder, font, max_width, ellipsis))
            return lines
        lines.append(ellipsize(word, font, max_width, ellipsis))
        index += 1

    return lines


@dataclass(frozen=True, slots=True)
class TextLineSpec:
    text: str
    typography_role: FontRole
    color: ColorToken | Color


def draw_text_cell(
    canvas: skia.Canvas,
    content: Rect,
    *,
    lines: list[TextLineSpec],
    text_left: float,
    text_width: float,
    typography: FontPalette,
    colors: ColorPalette,
) -> None:
    if not lines or text_width <= 0:
        return

    rendered: list[tuple[str, skia.Font, skia.Paint, float]] = []
    first_line_h = 0.0
    for idx, spec in enumerate(lines):
        if not spec.text:
            continue
        role_spec: FontSpec = getattr(typography, spec.typography_role)
        font = make_typography_font(role_spec)
        metrics = font.getMetrics()
        line_h = -metrics.fAscent + metrics.fDescent
        if idx == 0:
            first_line_h = line_h
        c = resolve_color(spec.color, colors)
        r, g, b, a = c.rgba
        paint = skia.Paint(AntiAlias=True)
        paint.setColor4f(skia.Color4f(r, g, b, a))
        rendered.append((ellipsize(spec.text, font, text_width), font, paint, line_h))

    if not rendered:
        return

    line_gap = max(2.0, first_line_h * 0.12)
    block_h = sum(line[3] for line in rendered) + line_gap * max(0, len(rendered) - 1)
    y = content.y + (content.height - block_h) / 2.0
    for idx, (text, font, paint, line_h) in enumerate(rendered):
        if text:
            line_baseline = y - font.getMetrics().fAscent
            canvas.drawString(text, text_left, line_baseline, font, paint)
        y += line_h + (line_gap if idx + 1 < len(rendered) else 0.0)
