"""Tests for std-edge-smoke-gl quality caps and defaults."""

from __future__ import annotations

from pixfabrica_std.particles.edge_smoke_gl import (
    _PREVIEW_OCTAVES_CAP,
    _PREVIEW_SHADOW_STEPS_CAP,
    _PREVIEW_STEPS_CAP,
    EdgeSmokeGL,
)


def test_defaults_match_shader_knobs() -> None:
    clip = EdgeSmokeGL(id="smoke")
    assert clip.edge == "bottom"
    assert clip.reach == 0.85
    assert clip.feather == 0.55
    assert clip.flow_speed == 2.55
    assert clip.cross_wind == 0.25
    assert clip.swirl == 2.5
    assert clip.churn_speed == 0.5
    assert clip.density == 1.3
    assert clip.slab_depth == 1.1
    assert clip.light_power == 1.4
    assert clip.ambient == 0.45
    assert clip.luma_alpha == 1.0
    assert clip.opacity == 1.0
    assert clip.steps == 64
    assert clip.octaves == 6
    assert clip.shadow_steps == 3


def test_preview_caps_quality() -> None:
    clip = EdgeSmokeGL(id="smoke", steps=96, octaves=6, shadow_steps=6)
    clip._for_preview = True
    steps, octaves, shadow_steps = clip._effective_quality()
    assert steps == _PREVIEW_STEPS_CAP
    assert octaves == _PREVIEW_OCTAVES_CAP
    assert shadow_steps == _PREVIEW_SHADOW_STEPS_CAP


def test_final_uses_user_quality() -> None:
    clip = EdgeSmokeGL(id="smoke", steps=80, octaves=5, shadow_steps=4)
    clip._for_preview = False
    assert clip._effective_quality() == (80, 5, 4)


def test_presets_exist() -> None:
    ids = {p["id"] for p in EdgeSmokeGL.clip_presets}
    assert ids == {"rising_fog", "side_drift"}
