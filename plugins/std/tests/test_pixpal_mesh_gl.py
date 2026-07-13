"""Tests for std-pixpal-mesh audio bass drive."""

from __future__ import annotations

import asyncio
from pathlib import Path

import numpy as np
import pytest

from pixfabrica_core.clips import JobInfo, PrepareContext
from pixfabrica_core.theme.color import ColorPalette
from pixfabrica_core.theme.typography import FontPalette
from pixfabrica_std.mesh.pixpal_mesh_gl import PixPalMeshGL
from pixfabrica_std.mesh.shader_helper import bass_zoom


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


def test_stem_analyzer_drums_bass_history_has_swing(tmp_path: Path) -> None:
    from pixfabrica_core.audio.analysis import StemAnalyzer

    audio = Path("web/public/preview-samples/sources/drums.mp3")
    if not audio.exists():
        pytest.skip("preview sample missing")

    tl = StemAnalyzer().analyze(audio, 0.0, 8.0, 30.0)
    clip = PixPalMeshGL(
        id="pix",
        bus_select="main",
        sensitivity=0.3,
        spin_bass=4.0,
        emissive_sensitivity=0.8,
    )
    ctx = _prepare_ctx(tmp_path, audio={"main": tl})
    asyncio.run(clip.prepare(ctx))

    bass = clip._bass_history  # noqa: SLF001
    assert float(np.percentile(bass, 95)) > 0.45
    assert float(np.std(bass)) > 0.12

    zooms = np.array([bass_zoom(True, clip.sensitivity, float(v)) for v in bass])
    assert float(np.percentile(zooms, 95)) > 1.12

    emissive = clip.emissive_factor * (1.0 + clip.emissive_sensitivity * bass)
    assert float(np.percentile(emissive, 95)) > clip.emissive_factor * 1.3


def test_bass_history_computed_even_when_mesh_cached(tmp_path: Path) -> None:
    from pixfabrica_core.audio.bus import N_SPECTRUM, AudioBusFrame

    frames = [
        AudioBusFrame(
            spectrum=[0.0] * N_SPECTRUM,
            bass=0.01 + i * 0.02,
            mid=0.0,
            high=0.0,
            beat=i % 8 == 0,
            amplitude=0.1 + i * 0.01,
        )
        for i in range(30)
    ]
    clip = PixPalMeshGL(id="pix", bus_select="main")
    ctx = _prepare_ctx(tmp_path, audio={"main": frames})
    asyncio.run(clip.prepare(ctx))
    assert clip._bass_history.size > 0  # noqa: SLF001
    assert float(clip._bass_history.max()) > 0.2  # noqa: SLF001

    asyncio.run(clip.prepare(ctx))
    assert float(clip._bass_history.max()) > 0.2  # noqa: SLF001
