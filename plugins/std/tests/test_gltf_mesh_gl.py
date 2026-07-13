"""Tests for std-gltf-mesh audio bass drive."""

from __future__ import annotations

import asyncio
from pathlib import Path

import numpy as np
import pytest

from pixfabrica_core.audio.bus import N_SPECTRUM, AudioBusFrame
from pixfabrica_core.clips import JobInfo, PrepareContext
from pixfabrica_core.theme.color import ColorPalette
from pixfabrica_core.theme.typography import FontPalette
from pixfabrica_std.mesh.gltf_mesh_gl import GltfMeshGL
from pixfabrica_std.mesh.shader_helper import bass_zoom, normalize_bus_scalar, precompute_bass_drive


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
    td.mkdir(exist_ok=True)
    cd.mkdir(exist_ok=True)
    return PrepareContext(job=ji, temp_dir=td, cache_dir=cd, audio=audio)


def test_normalize_bus_scalar_spreads_quiet_and_loud():
    raw = np.array([0.001, 0.01, 0.5], dtype=np.float32)
    out = normalize_bus_scalar(raw)
    assert out[0] == pytest.approx(0.0, abs=1e-4)
    assert out[-1] == pytest.approx(1.0, abs=1e-4)


def test_bass_zoom_uses_normalized_drive():
    assert bass_zoom(True, 0.3, 1.0) == pytest.approx(1.3)
    assert bass_zoom(True, 0.3, 0.076) == pytest.approx(1.0228)


def test_stem_analyzer_drums_bass_history_has_swing(tmp_path: Path) -> None:
    from pixfabrica_core.audio.analysis import StemAnalyzer

    audio = Path("web/public/preview-samples/sources/drums.mp3")
    if not audio.exists():
        pytest.skip("preview sample missing")

    tl = StemAnalyzer().analyze(audio, 0.0, 8.0, 30.0)
    clip = GltfMeshGL(id="mesh", bus_select="main", sensitivity=0.3, spin_bass=4.0)
    ctx = _prepare_ctx(tmp_path, audio={"main": tl})
    asyncio.run(clip.prepare(ctx))

    bass = clip._bass_history  # noqa: SLF001
    assert float(np.percentile(bass, 95)) > 0.45
    assert float(np.std(bass)) > 0.12

    zooms = np.array([bass_zoom(True, clip.sensitivity, float(v)) for v in bass])
    assert float(np.percentile(zooms, 95)) > 1.12


def test_precompute_bass_drive_from_flat_frames():
    frames = [
        AudioBusFrame(
            spectrum=[0.0] * N_SPECTRUM,
            bass=0.01,
            mid=0.0,
            high=0.0,
            beat=False,
            amplitude=0.01,
        ),
        AudioBusFrame(
            spectrum=[0.0] * N_SPECTRUM,
            bass=0.8,
            mid=0.0,
            high=0.0,
            beat=True,
            amplitude=0.8,
        ),
    ]
    out = precompute_bass_drive(frames, total=2, smoothing=0.0)
    assert out[1] > out[0]
    assert out[1] > 0.5
