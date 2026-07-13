"""Tests for layout spacer utility clips."""

from __future__ import annotations

from unittest.mock import MagicMock

from pixfabrica_core.catalog import infer_track_kind
from pixfabrica_core.clips import ClipCategory
from pixfabrica_std.utility.spacer import SpacerGL, SpacerSkia


def test_spacer_skia_registration() -> None:
    assert SpacerSkia.clip_type == "std-spacer-skia"
    assert SpacerSkia.clip_category == ClipCategory.UTILITY
    assert infer_track_kind(SpacerSkia) == "skia"


def test_spacer_gl_registration() -> None:
    assert SpacerGL.clip_type == "std-spacer-gl"
    assert SpacerGL.clip_category == ClipCategory.UTILITY
    assert infer_track_kind(SpacerGL) == "gl"


def test_spacer_draw_is_noop() -> None:
    canvas = MagicMock()
    ctx = MagicMock()
    ctx.canvas = canvas
    SpacerSkia(id="s1").draw(ctx)
    SpacerGL(id="g1").draw(ctx)
    canvas.assert_not_called()
