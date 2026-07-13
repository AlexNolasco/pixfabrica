"""Shared transport glyph rendering (play / pause / stop) for player UI clips."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path
from typing import Literal

import skia

from pixfabrica_core.theme.color import Color
from pixfabrica_std.player._svg_tint import tint_svg_bytes, tint_transport_button_svg

TransportState = Literal["play", "pause", "stop", "none"]
TransportGlyph = Literal["play", "pause", "stop"]

_TRANSPORT_FILES: dict[TransportGlyph, str] = {
    "play": "play.svg",
    "pause": "pause.svg",
    "stop": "stop.svg",
}

_TRANSPORT_OUTLINE_FILES: dict[TransportGlyph, str] = {
    "play": "play-outline.svg",
    "pause": "pause-outline.svg",
    "stop": "stop-outline.svg",
}

_TRANSPORT_BUTTON_FILES: dict[TransportGlyph, str] = {
    "play": "play-button.svg",
    "pause": "pause-button.svg",
    "stop": "stop-button.svg",
}

_GLYPH_DOM_CACHE: dict[
    tuple[TransportGlyph, tuple[float, float, float, float], bool], skia.SVGDOM
] = {}
_BUTTON_DOM_CACHE: dict[
    tuple[TransportGlyph, tuple[float, float, float, float], tuple[float, float, float, float]],
    skia.SVGDOM,
] = {}


def bundled_transport_svg_path(name: str) -> Path:
    return Path(str(files("pixfabrica_std") / "player" / "resources" / name))


def load_transport_dom(
    state: TransportGlyph, color: Color, *, outline: bool = False
) -> skia.SVGDOM | None:
    """Return a cached SVGDOM tinted to ``color`` (RGBA 0–1)."""
    key = (state, color.rgba, outline)
    cached = _GLYPH_DOM_CACHE.get(key)
    if cached is not None:
        return cached

    files_map = _TRANSPORT_OUTLINE_FILES if outline else _TRANSPORT_FILES
    filename = files_map[state]
    svg_bytes = bundled_transport_svg_path(filename).read_bytes()
    svg_bytes = tint_svg_bytes(svg_bytes, color, filled=not outline)

    dom = skia.SVGDOM.MakeFromStream(skia.MemoryStream(svg_bytes))
    if dom is not None:
        _GLYPH_DOM_CACHE[key] = dom
    return dom


def load_transport_button_dom(
    state: TransportGlyph,
    button_color: Color,
    glyph_color: Color,
) -> skia.SVGDOM | None:
    """Return a cached SVGDOM for a filled-circle + outline-glyph button."""
    key = (state, button_color.rgba, glyph_color.rgba)
    cached = _BUTTON_DOM_CACHE.get(key)
    if cached is not None:
        return cached

    filename = _TRANSPORT_BUTTON_FILES[state]
    svg_bytes = bundled_transport_svg_path(filename).read_bytes()
    svg_bytes = tint_transport_button_svg(svg_bytes, button_color, glyph_color)

    dom = skia.SVGDOM.MakeFromStream(skia.MemoryStream(svg_bytes))
    if dom is not None:
        _BUTTON_DOM_CACHE[key] = dom
    return dom


def draw_transport_icon(
    canvas: skia.Canvas,
    *,
    center_x: float,
    center_y: float,
    diameter: float,
    state: TransportState,
    color: Color,
    show_circle: bool = True,
    circle_fill: bool = False,
    glyph_color: Color | None = None,
    glyph_outline: bool = False,
    glyph_scale: float = 0.52,
    opacity: float = 1.0,
) -> None:
    """Draw a transport glyph centered at ``(center_x, center_y)``.

    ``circle_fill=True`` renders a bundled button SVG (filled disc + filled glyph).
    ``show_circle=True`` (default) draws a stroked ring around a standalone glyph.
    """
    if state == "none" or diameter <= 0 or opacity <= 0:
        return

    icon_color = glyph_color if glyph_color is not None else color

    if circle_fill:
        dom = load_transport_button_dom(state, color, icon_color)
        button_size = diameter
    else:
        radius = diameter / 2.0
        r, g, b, a = color.rgba
        if show_circle:
            ring = skia.Paint(AntiAlias=True)
            ring.setStyle(skia.Paint.kStroke_Style)
            ring.setStrokeWidth(max(1.0, diameter * 0.045))
            ring.setColor4f(skia.Color4f(r, g, b, a * opacity * 0.85))
            canvas.drawCircle(center_x, center_y, radius, ring)

        dom = load_transport_dom(state, icon_color, outline=glyph_outline)
        button_size = diameter * glyph_scale

    if dom is None:
        return

    dom.setContainerSize(skia.Size(button_size, button_size))

    canvas.save()
    canvas.translate(center_x, center_y)
    canvas.translate(-button_size / 2.0, -button_size / 2.0)

    if opacity < 1.0:
        layer = skia.Paint()
        layer.setAlphaf(opacity)
        canvas.saveLayer(skia.Rect.MakeWH(button_size, button_size), layer)
        dom.render(canvas)
        canvas.restore()
    else:
        dom.render(canvas)

    canvas.restore()
