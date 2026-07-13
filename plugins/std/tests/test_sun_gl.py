"""Tests for std-sun-gl registration, presets, shader compile, and brightness drive."""

from __future__ import annotations

import asyncio
from pathlib import Path

import numpy as np
import pytest

from pixfabrica_core.audio.bus import N_SPECTRUM, AudioBusFrame
from pixfabrica_core.clips import JobInfo, PrepareContext, TimeState
from pixfabrica_core.theme.color import ColorPalette
from pixfabrica_core.theme.typography import FontPalette
from pixfabrica_std.background.sun_gl import (
    SunGL,
    _live_brightness_from_frame,
    _precompute_brightness_history,
    _procedural_surface_rgb,
    _resolve_surface_rgb,
)


def test_clip_type_registered() -> None:
    assert SunGL.clip_type == "std-sun-gl"


def test_defaults() -> None:
    clip = SunGL(id="n1")
    assert clip.base_brightness == 0.35
    assert clip.sensitivity == 1.0
    assert clip.speed == 1.0
    assert clip.scale == 1.0
    assert clip.offset_x == 0.5
    assert clip.offset_y == 0.5
    assert clip.luma_alpha == 0.0
    assert clip.opacity == 1.0


def test_shader_compiles() -> None:
    import moderngl

    from pixfabrica_std.background.sun_gl import _FRAG, _VERT

    ctx = moderngl.create_standalone_context()
    ctx.program(vertex_shader=_VERT, fragment_shader=_FRAG)


def test_presets() -> None:
    presets = {p["id"]: p for p in SunGL.clip_presets}
    assert presets["classic"]["values"]["luma_alpha"] == 0.0
    assert presets["overlay"]["values"]["luma_alpha"] == 1.0
    assert presets["sunrise"]["values"]["offset_y"] == 0.85
    assert presets["red_giant"]["values"]["base_brightness"] == 0.45


def test_live_brightness_uses_mid_spectrum_bins() -> None:
    spec = [0.0] * N_SPECTRUM
    spec[4] = 0.8
    spec[10] = 0.4
    assert _live_brightness_from_frame(spec) == pytest.approx(0.3)


def test_brightness_history_additive_with_base() -> None:
    spec = [0.0] * N_SPECTRUM
    spec[4] = 1.0
    spec[10] = 1.0
    frames = [
        AudioBusFrame(
            spectrum=spec,
            bass=0.0,
            mid=0.0,
            high=0.0,
            beat=False,
            amplitude=0.0,
        )
    ]
    history = _precompute_brightness_history(
        frames,
        total=1,
        base_brightness=0.35,
        sensitivity=1.0,
    )
    assert history[0] == pytest.approx(0.85)


def test_brightness_history_no_bus_uses_base() -> None:
    history = _precompute_brightness_history(
        None,
        total=3,
        base_brightness=0.35,
        sensitivity=2.0,
    )
    assert np.all(history == pytest.approx(0.35))


def test_procedural_surface_is_neutral_grayscale() -> None:
    rgb = _procedural_surface_rgb(size=64)
    assert rgb.shape == (64, 64, 3)
    assert rgb.dtype == np.uint8
    r = rgb[..., 0].astype(np.float32)
    g = rgb[..., 1]
    assert float(np.std(r - g)) < 8.0
    assert float(np.mean(rgb)) > 20.0


def _prepare_ctx(tmp_path: Path, *, audio: dict | None = None) -> PrepareContext:
    ji = JobInfo(
        title="t",
        description="d",
        width=640,
        height=480,
        fps=30.0,
        duration=8.0,
        colors=ColorPalette(),
        typography=FontPalette(),
        locale="en",
    )
    td = tmp_path / "temp"
    cd = tmp_path / "cache"
    td.mkdir(exist_ok=True)
    cd.mkdir(exist_ok=True)
    return PrepareContext(job=ji, temp_dir=td, cache_dir=cd, audio=audio or {})


def test_prepare_builds_surface_and_brightness_history(tmp_path: Path) -> None:
    spec = [0.0] * N_SPECTRUM
    spec[4] = 0.5
    spec[10] = 0.5
    frames = [
        AudioBusFrame(
            spectrum=spec,
            bass=0.0,
            mid=0.0,
            high=0.0,
            beat=False,
            amplitude=0.0,
        )
    ]
    clip = SunGL(id="sun", bus_select="main", sensitivity=1.0)
    ctx = _prepare_ctx(tmp_path, audio={"main": frames})
    asyncio.run(clip.prepare(ctx))

    assert clip._surface_rgb is not None  # noqa: SLF001
    assert clip._surface_rgb.shape[2] == 3  # noqa: SLF001
    assert clip._brightness_history[0] > clip.base_brightness  # noqa: SLF001


def test_resolve_surface_rgb_falls_back_without_user_source(tmp_path: Path) -> None:
    ctx = _prepare_ctx(tmp_path)
    rgb = _resolve_surface_rgb(source=None, ctx=ctx, clip_id="sun", clip_type="std-sun-gl")
    assert rgb.shape[2] == 3


def _register_plugins() -> None:
    from pixfabrica_core.composition.registry import register_clip_type
    from pixfabrica_core.plugins.discovery import discover_plugins

    for plugin in discover_plugins()[0]:
        for clip_cls in plugin.clip_types:
            register_clip_type(clip_cls)


def _composite_sun(*, width: int, height: int) -> np.ndarray:
    from pixfabrica_core.composition.track import FillLayout, GLTrack
    from pixfabrica_core.fonts.skia_resolver import warmup_typography_palette
    from pixfabrica_core.theme.color import Color, ColorPalette
    from pixfabrica_renderer.compositor import Compositor

    colors = ColorPalette(
        primary=Color("#ffcc44"), secondary=Color("#ff6600"), background=Color("#000000")
    )
    ji = JobInfo(
        title="t",
        description="d",
        width=width,
        height=height,
        fps=30.0,
        duration=1.0,
        colors=colors,
        typography=FontPalette(),
        locale="en",
    )
    clip = SunGL(id="sun", start=0.0, duration=1.0, base_brightness=0.45)
    track = GLTrack(id="t", start=0.0, duration=1.0, layout=FillLayout(), clips=[clip])
    ctx = PrepareContext.from_env(ji)
    warmup_typography_palette(ji.typography)
    asyncio.run(track.prepare(ctx))
    compositor = Compositor([track], ji)
    try:
        return np.array(compositor.composite(TimeState(frame=0, t=0.0)).toarray())
    finally:
        compositor.release_worker_resources()


def test_no_ghost_disc_in_lower_right_corner() -> None:
    """Stereographic singularity must not paint a second sun at offset + (0.5, 0.5)."""
    _register_plugins()
    img = _composite_sun(width=640, height=480)
    luma = img[:, :, :3].astype(np.float32).mean(axis=2)
    # Sample a 24×24 patch at the lower-right corner (outside the centered disc).
    patch = luma[-24:, -24:]
    assert float(patch.max()) < 25.0
    assert float(patch.mean()) < 8.0
