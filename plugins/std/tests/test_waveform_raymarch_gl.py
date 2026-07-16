"""Tests for std-waveform-raymarch-gl band grouping, shaping, and bus reactivity."""

from __future__ import annotations

import asyncio
from pathlib import Path

import numpy as np
import pytest

from pixfabrica_core.audio.bus import N_SPECTRUM
from pixfabrica_core.clips import JobInfo, PrepareContext
from pixfabrica_core.theme.color import ColorPalette
from pixfabrica_core.theme.typography import FontPalette
from pixfabrica_std.audio.waveform_raymarch_gl import (
    _HEADROOM,
    _N_BANDS,
    WaveformRaymarchGL,
    _band_ranges,
    _mean_group,
    _shape_bands,
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


def test_clip_type():
    assert WaveformRaymarchGL.clip_type == "std-waveform-raymarch-gl"


def test_default_offset_y_is_centered():
    assert WaveformRaymarchGL.model_fields["offset_y"].default == pytest.approx(0.5)


def test_default_quality_is_full():
    assert WaveformRaymarchGL.model_fields["quality"].default == 90


def test_band_ranges_cover_spectrum_without_gaps():
    ranges = _band_ranges(_N_BANDS)
    assert len(ranges) == _N_BANDS
    assert ranges[0][0] == 0
    assert ranges[-1][1] == N_SPECTRUM - 1
    for i in range(len(ranges) - 1):
        assert ranges[i][1] + 1 == ranges[i + 1][0]


def test_mean_group_averages_range():
    freq = np.linspace(0.0, 1.0, N_SPECTRUM, dtype=np.float32)
    assert _mean_group(freq, 0, 3) == pytest.approx(float(freq[0:4].mean()))


def test_shape_bands_zero_when_silent():
    row = np.zeros(_N_BANDS, dtype=np.float32)
    out = _shape_bands(row, sensitivity=2.5)
    assert float(out.max()) == 0.0


def test_shape_bands_preserves_relative_levels():
    row = np.array([0.2, 0.5, 0.1, 0.3, 0.4], dtype=np.float32)
    out = _shape_bands(row, sensitivity=1.0)
    assert float(out[1]) > float(out[0]) > float(out[2])
    assert float(out.max()) < _HEADROOM + 0.01


def test_shape_bands_avoids_pegging_at_top():
    row = np.ones(_N_BANDS, dtype=np.float32) * 0.85
    out = _shape_bands(row, sensitivity=2.5)
    assert float(out.max()) <= _HEADROOM + 0.01


def test_bands_not_mirrored():
    spectrum = [0.1] * N_SPECTRUM
    spectrum[0] = 0.95
    spectrum[-1] = 0.2
    freq = np.asarray(spectrum, dtype="f4")
    ranges = _band_ranges(_N_BANDS)
    left = _mean_group(freq, *ranges[0])
    right = _mean_group(freq, *ranges[-1])
    assert left > right


def test_stem_analyzer_drums_has_dynamic_bands(tmp_path: Path) -> None:
    from pixfabrica_core.audio.analysis import StemAnalyzer

    audio = Path("web/public/preview-samples/sources/drums.mp3")
    if not audio.exists():
        pytest.skip("preview sample missing")

    tl = StemAnalyzer().analyze(audio, 0.0, 8.0, 30.0)
    clip = WaveformRaymarchGL(id="wave", bus_select="main", sensitivity=2.5, smoothing=0.45)
    ctx = _prepare_ctx(tmp_path, audio={"main": tl})
    asyncio.run(clip.prepare(ctx))

    history = clip._band_history  # noqa: SLF001
    assert history.shape[1] == _N_BANDS
    peaks = history.max(axis=1)
    assert float(np.percentile(peaks, 95)) > 0.2
    assert float(peaks.max()) <= _HEADROOM + 0.01
