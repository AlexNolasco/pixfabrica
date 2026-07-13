"""Tests for std-neon-ring-gl."""

from __future__ import annotations

import asyncio
from pathlib import Path

import moderngl
import pytest

from pixfabrica_core.audio.bus import N_SPECTRUM, AudioBusFrame
from pixfabrica_core.clips import JobInfo, PrepareContext
from pixfabrica_core.theme.color import ColorPalette, ColorToken
from pixfabrica_core.theme.typography import FontPalette
from pixfabrica_std.audio.neon_ring_gl import (
    _FRAG,
    _MAX_BARS,
    _MIN_BARS,
    _VERT,
    NeonRingGL,
    _sector_fx,
    _spectrum_bin_for_fx,
    resolve_palette_colors,
)


def _prepare_ctx(tmp_path: Path, *, duration_sec: float = 1.0) -> PrepareContext:
    ji = JobInfo(
        title="t",
        description="d",
        width=640,
        height=480,
        fps=30.0,
        duration=duration_sec,
        colors=ColorPalette(),
        typography=FontPalette(),
        locale="en",
    )
    td = tmp_path / "temp"
    cd = tmp_path / "cache"
    td.mkdir(exist_ok=True)
    cd.mkdir(exist_ok=True)
    return PrepareContext(job=ji, temp_dir=td, cache_dir=cd, audio={})


def test_clip_type_registered() -> None:
    assert NeonRingGL.clip_type == "std-neon-ring-gl"


def test_shader_compiles() -> None:
    ctx = moderngl.create_standalone_context()
    ctx.program(vertex_shader=_VERT, fragment_shader=_FRAG)


def test_bar_count_clamped() -> None:
    assert NeonRingGL(id="n", bar_count=10).bar_count == _MIN_BARS
    assert NeonRingGL(id="n", bar_count=200).bar_count == _MAX_BARS


def test_default_palette_when_colors_unset() -> None:
    palette = ColorPalette()
    stops = resolve_palette_colors(None, None, palette)
    assert len(stops) == 4
    assert stops[0][1] > 0.9


def test_theme_palette_when_colors_set() -> None:
    palette = ColorPalette()
    stops = resolve_palette_colors(ColorToken.PRIMARY, ColorToken.ACCENT, palette)
    assert stops[0] != stops[3]


def test_presets_include_dark_stage() -> None:
    presets = {p["id"]: p for p in NeonRingGL.clip_presets}
    assert "default" in presets
    assert presets["dark_stage"]["values"]["color_background"] == "background"


def test_mirrored_sector_fx_is_symmetric() -> None:
    n = 90
    assert _sector_fx(0, n) == pytest.approx(_sector_fx(n // 2, n), abs=1e-6)


def test_precompute_bar_history_with_bus(tmp_path: Path) -> None:
    clip = NeonRingGL(id="n", bar_count=64, bus_select="main")
    frames = [
        AudioBusFrame(
            amplitude=0.5,
            bass=0.4,
            mid=0.3,
            high=0.2,
            beat=False,
            spectrum=[0.1 * (i % 8) for i in range(N_SPECTRUM)],
        )
        for _ in range(30)
    ]
    pctx = _prepare_ctx(tmp_path, duration_sec=1.0)
    pctx = PrepareContext(
        job=pctx.job,
        temp_dir=pctx.temp_dir,
        cache_dir=pctx.cache_dir,
        audio={"main": frames},
    )
    asyncio.run(clip.prepare(pctx))
    assert clip._has_bus_timeline is True
    assert clip._bar_history.shape[0] == pctx.job.total_frames
    assert float(clip._bar_history[10, 0]) >= 0.0


def test_spectrum_bin_for_fx_within_range() -> None:
    idx = _spectrum_bin_for_fx(0.5)
    assert 0 <= idx < N_SPECTRUM
