"""Tests for std-spectrum-bars StemAnalyzer reactivity."""

from __future__ import annotations

import asyncio
from pathlib import Path

import numpy as np
import pytest

from pixfabrica_core.clips import JobInfo, PrepareContext
from pixfabrica_core.theme.color import ColorPalette
from pixfabrica_core.theme.typography import FontPalette
from pixfabrica_std.audio.spectrum_bars import (
    SpectrumBars,
    _edge_envelope,
    _shape_half_row,
    _soft_saturate,
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
    td.mkdir(exist_ok=True)
    cd.mkdir(exist_ok=True)
    return PrepareContext(job=ji, temp_dir=td, cache_dir=cd, audio=audio)


def test_edge_envelope_favors_outer_bars():
    env = _edge_envelope(32)
    assert env[0] == pytest.approx(1.0, abs=1e-4)
    assert env[-1] < env[0]
    assert env[-1] >= 0.12


def test_shape_half_row_preserves_frame_coherence():
    row = np.array([0.2, 0.8, 0.4, 0.6], dtype=np.float32)
    env = _edge_envelope(4)
    out = _shape_half_row(row, env, drive=1.0, sensitivity=1.0)
    assert float(out.max()) < 1.0
    assert out[0] > out[-1]


def test_soft_saturate_avoids_hard_pin():
    row = np.ones(4, dtype=np.float32)
    out = _soft_saturate(row, gain=3.45)
    assert float(out.max()) < 0.999
    assert float(out.max()) > 0.7


def test_high_sensitivity_drums_avoids_flat_top_bars(tmp_path: Path) -> None:
    from pixfabrica_core.audio.analysis import StemAnalyzer

    audio = Path("web/public/preview-samples/sources/drums.mp3")
    if not audio.exists():
        pytest.skip("preview sample missing")

    tl = StemAnalyzer().analyze(audio, 0.0, 8.0, 30.0)
    clip = SpectrumBars(id="sb", bus_select="main", sensitivity=3.45, smoothing=0.5)
    ctx = _prepare_ctx(tmp_path, audio={"main": tl})
    asyncio.run(clip.prepare(ctx))

    history = clip._bar_history[:, : clip.bar_count]  # noqa: SLF001
    assert float((history >= 0.999).mean()) < 0.001
    peaks = history.max(axis=1)
    assert float(np.percentile(peaks, 95)) > 0.45
    assert float(np.std(peaks)) > 0.08


def test_stem_analyzer_drums_has_dynamic_bar_heights(tmp_path: Path) -> None:
    from pixfabrica_core.audio.analysis import StemAnalyzer

    audio = Path("web/public/preview-samples/sources/drums.mp3")
    if not audio.exists():
        pytest.skip("preview sample missing")

    tl = StemAnalyzer().analyze(audio, 0.0, 8.0, 30.0)
    clip = SpectrumBars(id="sb", bus_select="main", sensitivity=2.5, smoothing=0.5)
    ctx = _prepare_ctx(tmp_path, audio={"main": tl})
    asyncio.run(clip.prepare(ctx))

    half = clip.bar_count // 2
    history = clip._bar_history[:, : clip.bar_count]  # noqa: SLF001
    left = history[:, :half]
    center = history[:, half - 2 : half]
    assert float(np.mean(left)) > float(np.mean(center))

    peaks = history.max(axis=1)
    assert float(np.percentile(peaks, 95)) > 0.5
    assert float(np.std(peaks)) > 0.1
    assert float(peaks.max()) <= 1.0
