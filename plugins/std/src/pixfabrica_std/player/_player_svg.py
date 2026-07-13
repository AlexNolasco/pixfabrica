"""Load and draw bundled player UI SVG assets."""

from __future__ import annotations

from typing import Literal

import skia

from pixfabrica_core.theme.color import Color
from pixfabrica_std.player._svg_tint import tint_svg_bytes
from pixfabrica_std.player.transport_icon import bundled_transport_svg_path

RowIconName = Literal["play", "heart", "message-circle", "repeat"]

_ROW_FILES: dict[RowIconName, str] = {
    "play": "play.svg",
    "heart": "heart.svg",
    "message-circle": "message-circle.svg",
    "repeat": "repeat.svg",
}

_DOM_CACHE: dict[tuple[str, tuple[float, float, float, float]], skia.SVGDOM] = {}


def _tint_svg(filename: str, color: Color) -> skia.SVGDOM | None:
    key = (filename, color.rgba)
    cached = _DOM_CACHE.get(key)
    if cached is not None:
        return cached

    svg_bytes = bundled_transport_svg_path(filename).read_bytes()
    svg_bytes = tint_svg_bytes(svg_bytes, color, filled=(filename == "play.svg"))
    dom = skia.SVGDOM.MakeFromStream(skia.MemoryStream(svg_bytes))
    if dom is not None:
        _DOM_CACHE[key] = dom
    return dom


def draw_row_icon(
    canvas: skia.Canvas,
    *,
    name: RowIconName,
    x: float,
    y: float,
    size: float,
    color: Color,
) -> None:
    """Draw icon with top-left at ``(x, y)``."""
    if size <= 0:
        return

    dom = _tint_svg(_ROW_FILES[name], color)
    if dom is None:
        return

    dom.setContainerSize(skia.Size(size, size))
    canvas.save()
    canvas.translate(x, y)
    dom.render(canvas)
    canvas.restore()
