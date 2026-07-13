"""Tests for std-dying-universe-gl audio drive."""

from __future__ import annotations

import asyncio
from pathlib import Path

import numpy as np
import pytest

from pixfabrica_core.clips import JobInfo, PrepareContext
from pixfabrica_core.theme.color import ColorPalette
from pixfabrica_core.theme.typography import FontPalette
from pixfabrica_std.mesh.shader_helper import precompute_bus_drives
from pixfabrica_std.particles.dying_universe_gl import DyingUniverseGL


def _prepare_ctx(tmp_path: Path, *, audio: dict) -> PrepareContext:
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
    tmp_path.mkdir(parents=True, exist_ok=True)
    td.mkdir(exist_ok=True)
    cd.mkdir(exist_ok=True)
    return PrepareContext(job=ji, temp_dir=td, cache_dir=cd, audio=audio)


def test_precompute_bus_drives_spreads_each_channel():
    from pixfabrica_core.audio.bus import N_SPECTRUM, AudioBusFrame

    frames = [
        AudioBusFrame(
            spectrum=[0.0] * N_SPECTRUM,
            bass=0.01,
            mid=0.02,
            high=0.0,
            beat=False,
            amplitude=0.03,
        ),
        AudioBusFrame(
            spectrum=[0.0] * N_SPECTRUM,
            bass=0.8,
            mid=0.5,
            high=0.0,
            beat=True,
            amplitude=0.9,
        ),
    ]
    bass, mid, _, amp = precompute_bus_drives(frames, total=2, smoothing=0.0)
    assert bass[1] > bass[0]
    assert mid[1] > mid[0]
    assert amp[1] > amp[0]
    assert bass[1] > 0.5


def test_stem_analyzer_drums_has_dynamic_bus_drives(tmp_path: Path) -> None:
    from pixfabrica_core.audio.analysis import StemAnalyzer

    audio = Path("web/public/preview-samples/sources/drums.mp3")
    if not audio.exists():
        pytest.skip("preview sample missing")

    tl = StemAnalyzer().analyze(audio, 0.0, 8.0, 30.0)
    clip = DyingUniverseGL(id="du", bus_select="main", sensitivity=2.5, bass_sensitivity=0.5)
    ctx = _prepare_ctx(tmp_path, audio={"main": tl})
    asyncio.run(clip.prepare(ctx))

    bass = clip._bass_history  # noqa: SLF001
    mid = clip._mid_history  # noqa: SLF001
    amp = clip._amp_history  # noqa: SLF001
    assert float(np.percentile(bass, 95)) > 0.45
    assert float(np.std(bass)) > 0.12
    assert float(np.percentile(mid, 95)) > 0.25
    assert float(np.percentile(amp, 95)) > 0.45

    star_boost = 1.0 + np.clip(bass * clip.sensitivity, 0.0, 1.0) * clip.bass_sensitivity
    assert float(np.percentile(star_boost, 95)) > 1.2

    brightness = 0.8 + np.clip(amp * clip.sensitivity, 0.0, 1.0) * 0.4
    assert float(np.percentile(brightness, 95)) > 1.0
