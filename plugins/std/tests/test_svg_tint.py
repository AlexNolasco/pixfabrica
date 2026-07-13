"""Tests for SVG tinting used by player icons."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from pixfabrica_core.theme.color import Color
from pixfabrica_std.player._svg_tint import tint_svg_bytes, tint_transport_button_svg
from pixfabrica_std.player.transport_icon import bundled_transport_svg_path


def test_tint_transport_svgs_set_explicit_fill() -> None:
    color = Color("#336699")
    for name in ("play.svg", "pause.svg", "stop.svg"):
        tinted = tint_svg_bytes(bundled_transport_svg_path(name).read_bytes(), color, filled=True)
        root = ET.fromstring(tinted)
        shapes = [elem for elem in root.iter() if elem.tag.rsplit("}", 1)[-1] in {"path", "rect"}]
        assert shapes
        assert all(elem.get("fill") == "#336699" for elem in shapes)


def test_tint_transport_button_svg_sets_circle_and_glyph_colors() -> None:
    tinted = tint_transport_button_svg(
        bundled_transport_svg_path("play-button.svg").read_bytes(),
        Color("#336699"),
        Color("#121212"),
    )
    root = ET.fromstring(tinted)
    circle = next(elem for elem in root.iter() if elem.tag.rsplit("}", 1)[-1] == "circle")
    path = next(elem for elem in root.iter() if elem.tag.rsplit("}", 1)[-1] == "path")
    assert circle.get("fill") == "#336699"
    assert path.get("fill") == "#121212"
    assert path.get("stroke") is None


def test_tint_outline_transport_svgs_set_explicit_stroke() -> None:
    color = Color("#336699")
    tinted = tint_svg_bytes(
        bundled_transport_svg_path("pause-outline.svg").read_bytes(),
        color,
        filled=False,
    )
    root = ET.fromstring(tinted)
    lines = [elem for elem in root.iter() if elem.tag.rsplit("}", 1)[-1] == "line"]
    assert len(lines) == 2
    assert all(elem.get("stroke") == "#336699" for elem in lines)
    assert all(elem.get("fill") == "none" for elem in lines)
