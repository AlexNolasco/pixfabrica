"""Shared layout helpers for std-image placement."""

from __future__ import annotations

from typing import Literal

from pixfabrica_core.graphics import Rect

ImageAlign = Literal[
    "topLeading",
    "top",
    "topTrailing",
    "leading",
    "center",
    "trailing",
    "bottomLeading",
    "bottom",
    "bottomTrailing",
]

# Fraction of image width/height for the align anchor (0 = leading/top, 1 = trailing/bottom).
IMAGE_ALIGN_ANCHOR: dict[str, tuple[float, float]] = {
    "topLeading": (0.0, 0.0),
    "top": (0.5, 0.0),
    "topTrailing": (1.0, 0.0),
    "leading": (0.0, 0.5),
    "center": (0.5, 0.5),
    "trailing": (1.0, 0.5),
    "bottomLeading": (0.0, 1.0),
    "bottom": (0.5, 1.0),
    "bottomTrailing": (1.0, 1.0),
}

# Matching bounds anchor fractions used when snapping align presets in the UI.
ALIGN_PRESET_OFFSETS: dict[str, tuple[float, float]] = {
    "topLeading": (0.0, 0.0),
    "top": (0.5, 0.0),
    "topTrailing": (1.0, 0.0),
    "leading": (0.0, 0.5),
    "center": (0.5, 0.5),
    "trailing": (1.0, 0.5),
    "bottomLeading": (0.0, 1.0),
    "bottom": (0.5, 1.0),
    "bottomTrailing": (1.0, 1.0),
}


def compute_image_draw_rect(
    bounds: Rect,
    *,
    width_frac: float,
    src_w: float,
    src_h: float,
    offset_x: float,
    offset_y: float,
    align: str,
) -> tuple[float, float, float, float]:
    """Return ``(x, y, draw_w, draw_h)`` in canvas space for the image rect."""
    if src_w <= 0 or src_h <= 0 or width_frac <= 0:
        return bounds.x, bounds.y, 0.0, 0.0

    draw_w = width_frac * float(bounds.width)
    draw_h = draw_w * (src_h / src_w)

    ax, ay = IMAGE_ALIGN_ANCHOR.get(align, (0.5, 0.5))
    anchor_x = bounds.x + offset_x * float(bounds.width)
    anchor_y = bounds.y + offset_y * float(bounds.height)

    x = anchor_x - ax * draw_w
    y = anchor_y - ay * draw_h
    return x, y, draw_w, draw_h


def compute_text_draw_rect(
    bounds: Rect,
    *,
    text_w: float,
    text_h: float,
    offset_x: float,
    offset_y: float,
    align: str,
) -> tuple[float, float, float, float]:
    """Return ``(x, y, draw_w, draw_h)`` for a text bounding box in canvas space."""
    if text_w <= 0.0 or text_h <= 0.0:
        return bounds.x, bounds.y, 0.0, 0.0

    ax, ay = IMAGE_ALIGN_ANCHOR.get(align, (0.5, 0.5))
    anchor_x = bounds.x + offset_x * float(bounds.width)
    anchor_y = bounds.y + offset_y * float(bounds.height)

    x = anchor_x - ax * text_w
    y = anchor_y - ay * text_h
    return x, y, text_w, text_h
