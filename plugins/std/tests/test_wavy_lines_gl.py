"""Tests for std-wavy-lines-gl spectrum drive and job-wide normalization."""

from __future__ import annotations

import asyncio
from pathlib import Path

import numpy as np
import pytest

from pixfabrica_core.audio.bus import N_SPECTRUM, AudioBusFrame
from pixfabrica_core.clips import JobInfo, PrepareContext
from pixfabrica_core.theme.color import ColorPalette
from pixfabrica_core.theme.typography import FontPalette
from pixfabrica_std.audio.wavy_lines_gl import (
    WavyLinesGL,
    _normalize_columns,
)


def _prepare_ctx(
    tmp_path: Path,
    *,
    audio: dict | None = None,
    duration_sec: float = 8.0,
) -> PrepareContext:
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
    return PrepareContext(job=ji, temp_dir=td, cache_dir=cd, audio=audio or {})


def test_normalize_columns_spreads_quiet_and_loud_rows():
    raw = np.array(
        [
            [0.0, 0.0],
            [0.01, 0.02],
            [1.0, 0.5],
        ],
        dtype=np.float32,
    )
    out = _normalize_columns(raw)
    assert out[0, 0] == pytest.approx(0.0, abs=1e-5)
    assert out[-1, 0] == pytest.approx(1.0, abs=1e-4)
    assert out[-1, 1] == pytest.approx(1.0, abs=1e-4)


def test_per_frame_peak_norm_not_saturated_on_drums(tmp_path: Path) -> None:
    """Regression: per-frame max norm used to pin every frame at sensitivity cap."""
    from pixfabrica_core.audio.analysis import StemAnalyzer

    audio = Path("web/public/preview-samples/sources/drums.mp3")
    if not audio.exists():
        pytest.skip("preview sample missing")

    tl = StemAnalyzer().analyze(audio, 0.0, 8.0, 30.0)
    clip = WavyLinesGL(id="w", bus_select="main", sensitivity=2.5, smoothing=0.05)
    ctx = _prepare_ctx(tmp_path, audio={"main": tl})
    asyncio.run(clip.prepare(ctx))

    frame_peaks = clip._line_history.max(axis=1)  # noqa: SLF001
    assert float(np.std(frame_peaks)) > 0.15
    assert float(np.percentile(frame_peaks, 10)) < float(np.percentile(frame_peaks, 95))
    assert float(frame_peaks.max()) <= 3.0


def test_glow_intensity_defaults_off() -> None:
    clip = WavyLinesGL(id="w", bus_select="main")
    assert clip.glow_intensity == 0.0


def test_bass_history_uses_job_wide_range(tmp_path: Path) -> None:
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
            bass=0.5,
            mid=0.0,
            high=0.0,
            beat=True,
            amplitude=0.5,
        ),
    ]
    clip = WavyLinesGL(id="w", bus_select="main", smoothing=0.0)
    ctx = _prepare_ctx(tmp_path, audio={"main": frames}, duration_sec=2 / 30.0)
    asyncio.run(clip.prepare(ctx))
    bass = clip._bass_history  # noqa: SLF001
    assert bass.shape == (2,)
    assert bass[1] > bass[0]
    assert bass[1] > 0.5
