"""Tests for std-warped-grid-gl bus spectrogram and glow drive."""

from __future__ import annotations

import asyncio
from pathlib import Path

import numpy as np
import pytest

from pixfabrica_core.clips import JobInfo, PrepareContext
from pixfabrica_core.theme.color import ColorPalette
from pixfabrica_core.theme.typography import FontPalette
from pixfabrica_std.background.warped_grid_gl import (
    WarpedGridGL,
    _build_spectrogram_rgb,
)


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


def test_build_spectrogram_rgb_uses_job_wide_range():
    from pixfabrica_core.audio.bus import N_SPECTRUM, AudioBusFrame

    quiet = AudioBusFrame(
        spectrum=[0.001] * N_SPECTRUM,
        bass=0.01,
        mid=0.0,
        high=0.0,
        beat=False,
        amplitude=0.01,
    )
    loud = AudioBusFrame(
        spectrum=[0.02] * N_SPECTRUM,
        bass=0.8,
        mid=0.0,
        high=0.0,
        beat=True,
        amplitude=0.9,
    )
    rgb = _build_spectrogram_rgb([quiet, loud], width=32, sensitivity=2.5)
    assert float(rgb.max()) == 255.0
    assert float(rgb.mean()) > 1.0


def test_stem_analyzer_drums_spectrogram_has_contrast(tmp_path: Path) -> None:
    from pixfabrica_core.audio.analysis import StemAnalyzer

    audio = Path("web/public/preview-samples/sources/drums.mp3")
    if not audio.exists():
        pytest.skip("preview sample missing")

    tl = StemAnalyzer().analyze(audio, 0.0, 8.0, 30.0)
    rgb = _build_spectrogram_rgb(tl, sensitivity=2.5)
    assert float(np.percentile(rgb, 95)) > 80.0
    assert float(rgb.std()) > 15.0


def test_prepare_builds_heightmap_and_amp_history(tmp_path: Path) -> None:
    from pixfabrica_core.audio.analysis import StemAnalyzer

    audio = Path("web/public/preview-samples/sources/drums.mp3")
    if not audio.exists():
        pytest.skip("preview sample missing")

    tl = StemAnalyzer().analyze(audio, 0.0, 8.0, 30.0)
    clip = WarpedGridGL(id="wg", bus_select="main", sensitivity=2.5)
    ctx = _prepare_ctx(tmp_path, audio={"main": tl})
    asyncio.run(clip.prepare(ctx))

    assert clip._heightmap_rgb is not None  # noqa: SLF001
    assert float(np.percentile(clip._heightmap_rgb, 95)) > 80.0  # noqa: SLF001
    amp = clip._amp_history  # noqa: SLF001
    assert float(np.percentile(amp, 95)) > 0.45
