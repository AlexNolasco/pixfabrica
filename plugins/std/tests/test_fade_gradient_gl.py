"""Tests for std-fade-gradient-gl registration and shader compile."""

from __future__ import annotations

from pixfabrica_core.catalog import infer_track_kind
from pixfabrica_core.clips import ClipCategory, ClipTag
from pixfabrica_std.background.fade_gradient_gl import FadeGradientGL


def test_clip_type_registered() -> None:
    assert FadeGradientGL.clip_type == "std-fade-gradient-gl"
    assert FadeGradientGL.clip_category == ClipCategory.BACKGROUND
    assert ClipTag.GRADIENT in FadeGradientGL.clip_tags
    assert infer_track_kind(FadeGradientGL) == "gl"


def test_defaults() -> None:
    clip = FadeGradientGL(id="n1")
    assert clip.direction == "to bottom"
    assert clip.brightness == 1.0
    assert clip.opacity == 1.0


def test_shader_compiles() -> None:
    import moderngl

    from pixfabrica_std.background.fade_gradient_gl import _FRAG, _VERT

    ctx = moderngl.create_standalone_context()
    ctx.program(vertex_shader=_VERT, fragment_shader=_FRAG)
