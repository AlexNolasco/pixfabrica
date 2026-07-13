"""Tests for std-hyperspace-gl registration, presets, shader compile, and gust warp."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from pixfabrica_core.audio.bus import AudioBusFrame
from pixfabrica_core.clips import JobInfo, PrepareContext
from pixfabrica_core.theme.color import ColorPalette, ColorToken
from pixfabrica_core.theme.typography import FontPalette
from pixfabrica_std.background.hyperspace_gl import (
    _GUST_BOOST,
    _NOISE_SIZE,
    _STAR_SPARSE_FRACTION,
    HyperspaceGL,
    _precompute_scroll_and_gust,
    _procedural_depth_noise_rgb,
    _resolve_surface_rgb,
)


def test_clip_type_registered() -> None:
    assert HyperspaceGL.clip_type == "std-hyperspace-gl"


def test_defaults() -> None:
    clip = HyperspaceGL(id="n1")
    assert clip.speed == 1.0
    assert clip.brightness == 1.0
    assert clip.luma_alpha == 0.0
    assert clip.opacity == 1.0


def test_shader_compiles() -> None:
    import moderngl

    from pixfabrica_std.background.hyperspace_gl import _FRAG, _VERT

    ctx = moderngl.create_standalone_context()
    ctx.program(vertex_shader=_VERT, fragment_shader=_FRAG)


def test_presets() -> None:
    presets = {p["id"]: p for p in HyperspaceGL.clip_presets}
    assert presets["classic"]["values"]["luma_alpha"] == 0.0
    assert presets["overlay"]["values"]["luma_alpha"] == 1.0
    assert presets["heavy_warp"]["values"]["speed"] == 1.8
    assert presets["slow_drift"]["values"]["speed"] == 0.5
    assert presets["sunset_warp"]["values"]["color_warm"] == ColorToken.SECONDARY
    assert presets["sunset_warp"]["values"]["color_cool"] == ColorToken.PRIMARY


def test_resolve_surface_rgb_falls_back_without_user_source(tmp_path: Path) -> None:
    ji = JobInfo(
        title="t",
        description="d",
        width=640,
        height=360,
        fps=30.0,
        duration=1.0,
        colors=ColorPalette(),
        typography=FontPalette(),
        locale="en",
    )
    td = tmp_path / "temp"
    cd = tmp_path / "cache"
    td.mkdir(exist_ok=True)
    cd.mkdir(exist_ok=True)
    ctx = PrepareContext(job=ji, temp_dir=td, cache_dir=cd)
    rgb = _resolve_surface_rgb(source=None, ctx=ctx, clip_id="hs", clip_type="std-hyperspace-gl")
    assert rgb.ndim == 3
    assert rgb.shape[2] == 3


def test_procedural_depth_noise_rgb_shape_and_sparsity() -> None:
    rgb = _procedural_depth_noise_rgb(_NOISE_SIZE)
    assert rgb.shape == (_NOISE_SIZE, _NOISE_SIZE, 3)
    depth = rgb[..., 0].astype(np.float32) / 255.0
    star_cells = (depth < 0.5).mean()
    assert star_cells == pytest.approx(_STAR_SPARSE_FRACTION, rel=0.25)


def test_no_bus_scroll_is_linear_and_gust_flat() -> None:
    scroll, gust = _precompute_scroll_and_gust(
        total_frames=30,
        fps=30.0,
        speed=1.0,
        bus_select=None,
        bus_frames=None,
    )
    assert scroll.shape == (30,)
    assert gust.shape == (30,)
    assert scroll[0] == pytest.approx(0.0)
    assert scroll[1] == pytest.approx(1.0 / 30.0)
    assert gust.max() == 1.0


def test_bus_onset_accelerates_scroll_and_spikes_gust() -> None:
    frames = [AudioBusFrame.zero() for _ in range(60)]
    frames[10] = AudioBusFrame.zero().model_copy(update={"onset": True, "amplitude": 0.8})

    steady_scroll, steady_gust = _precompute_scroll_and_gust(
        total_frames=60,
        fps=30.0,
        speed=1.0,
        bus_select=None,
        bus_frames=None,
    )
    gusty_scroll, gusty_gust = _precompute_scroll_and_gust(
        total_frames=60,
        fps=30.0,
        speed=1.0,
        bus_select="main",
        bus_frames=frames,
    )

    assert gusty_scroll[20] > steady_scroll[20]
    assert gusty_gust[10] == pytest.approx(_GUST_BOOST)
    assert gusty_gust.max() >= _GUST_BOOST


def test_gust_boost_constant_is_punchy() -> None:
    assert _GUST_BOOST >= 4.0
