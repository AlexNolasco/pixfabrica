"""Tint bundled SVG bytes for Skia's SVGDOM (no CSS inheritance)."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from pixfabrica_core.theme.color import Color
from pixfabrica_std.image.svg_icon import _normalize_svg

_SHAPE_TAGS = frozenset({"path", "rect", "circle", "ellipse", "polygon", "polyline", "line"})


def _color_hex(color: Color) -> str:
    r, g, b, _ = color.rgba
    return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"


def tint_svg_bytes(svg_bytes: bytes, color: Color, *, filled: bool) -> bytes:
    """Apply ``color`` to shape elements in a way Skia SVGDOM understands."""
    svg_bytes = _normalize_svg(svg_bytes)
    hex_color = _color_hex(color)
    try:
        root = ET.fromstring(svg_bytes)
        for elem in root.iter():
            tag = elem.tag.rsplit("}", 1)[-1]
            if tag not in _SHAPE_TAGS:
                continue
            if filled:
                elem.set("fill", hex_color)
                elem.attrib.pop("stroke", None)
                elem.attrib.pop("stroke-width", None)
            else:
                elem.set("stroke", hex_color)
                elem.set("fill", "none")
        if filled:
            root.set("fill", "none")
        return ET.tostring(root, encoding="unicode", xml_declaration=False).encode("utf-8")
    except ET.ParseError:
        return (
            svg_bytes.decode("utf-8", errors="replace").replace("currentColor", hex_color).encode()
        )


def tint_transport_button_svg(
    svg_bytes: bytes,
    button_color: Color,
    glyph_color: Color,
) -> bytes:
    """Tint a bundled transport button SVG (filled circle + filled glyph)."""
    svg_bytes = _normalize_svg(svg_bytes)
    button_hex = _color_hex(button_color)
    glyph_hex = _color_hex(glyph_color)
    try:
        root = ET.fromstring(svg_bytes)
        for elem in root.iter():
            tag = elem.tag.rsplit("}", 1)[-1]
            if tag not in _SHAPE_TAGS:
                continue
            if tag == "circle":
                elem.set("fill", button_hex)
            else:
                elem.set("fill", glyph_hex)
            elem.attrib.pop("stroke", None)
            elem.attrib.pop("stroke-width", None)
        root.set("fill", "none")
        return ET.tostring(root, encoding="unicode", xml_declaration=False).encode("utf-8")
    except ET.ParseError:
        text = svg_bytes.decode("utf-8", errors="replace")
        return text.replace("__BUTTON__", button_hex).replace("__GLYPH__", glyph_hex).encode()
