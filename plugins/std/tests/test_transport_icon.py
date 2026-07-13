"""Tests for shared transport icon assets."""

from __future__ import annotations

import skia

from pixfabrica_core.theme.color import Color
from pixfabrica_std.player.transport_icon import (
    bundled_transport_svg_path,
    load_transport_button_dom,
    load_transport_dom,
)


def test_bundled_transport_svgs_exist() -> None:
    for name in (
        "play.svg",
        "pause.svg",
        "stop.svg",
        "play-outline.svg",
        "pause-outline.svg",
        "stop-outline.svg",
        "play-button.svg",
        "pause-button.svg",
        "stop-button.svg",
    ):
        assert bundled_transport_svg_path(name).is_file()


def test_load_transport_dom_parses_all_states() -> None:
    color = Color("#336699")
    for state in ("play", "pause", "stop"):
        dom = load_transport_dom(state, color)
        assert dom is not None
        assert isinstance(dom, skia.SVGDOM)
        outline_dom = load_transport_dom(state, color, outline=True)
        assert outline_dom is not None
        assert isinstance(outline_dom, skia.SVGDOM)


def test_load_transport_button_dom_parses_all_states() -> None:
    button = Color("#336699")
    glyph = Color("#121212")
    for state in ("play", "pause", "stop"):
        dom = load_transport_button_dom(state, button, glyph)
        assert dom is not None
        assert isinstance(dom, skia.SVGDOM)


def test_draw_transport_icon_none_is_noop() -> None:
    from unittest.mock import MagicMock

    from pixfabrica_std.player.transport_icon import draw_transport_icon

    canvas = MagicMock()
    draw_transport_icon(
        canvas,
        center_x=50.0,
        center_y=50.0,
        diameter=40.0,
        state="none",
        color=Color("#ffffff"),
    )
    canvas.drawCircle.assert_not_called()


def test_draw_transport_icon_filled_button_uses_svg_not_skia_circle() -> None:
    from unittest.mock import MagicMock, patch

    from pixfabrica_std.player.transport_icon import draw_transport_icon

    canvas = MagicMock()
    with patch("pixfabrica_std.player.transport_icon.load_transport_button_dom", return_value=None):
        draw_transport_icon(
            canvas,
            center_x=50.0,
            center_y=50.0,
            diameter=40.0,
            state="play",
            color=Color("#336699"),
            show_circle=False,
            circle_fill=True,
            glyph_color=Color("#121212"),
        )
    canvas.drawCircle.assert_not_called()
