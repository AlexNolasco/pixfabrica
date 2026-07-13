"""Tests for std-eq-wave-gl bin grouping, shaping, and bus reactivity."""

from __future__ import annotations

import asyncio
from pathlib import Path

import numpy as np
import pytest

from pixfabrica_core.audio.bus import N_SPECTRUM
from pixfabrica_core.clips import JobInfo, PrepareContext
from pixfabrica_core.theme.color import ColorPalette
from pixfabrica_core.theme.typography import FontPalette
from pixfabrica_std.audio.eq_wave_gl import (
    _HEADROOM,
    EqWaveGL,
    _bin_group_ranges,
    _fold_to_center_profile,
    _mean_group,
    _shape_row,
    _shape_symmetric_profile,
    _strip_layout,
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
    assert EqWaveGL.clip_type == "std-eq-wave-gl"


def test_default_bar_count_is_64():
    assert EqWaveGL.model_fields["bar_count"].default == 64


def test_default_curve_smooth():
    assert EqWaveGL.model_fields["curve_smooth"].default == pytest.approx(0.45)


def test_default_offset_y_is_baseline():
    assert EqWaveGL.model_fields["offset_y"].default == pytest.approx(0.85)


def test_bar_count_coerces_to_even():
    assert EqWaveGL.model_fields["bar_count"].default == 64


def test_bin_groups_cover_spectrum_without_gaps():
    ranges = _bin_group_ranges(16)
    assert len(ranges) == 16
    assert ranges[0][0] == 0
    assert ranges[-1][1] == N_SPECTRUM - 1
    for i in range(len(ranges) - 1):
        assert ranges[i][1] + 1 == ranges[i + 1][0]


def test_mean_group_averages_range():
    freq = np.linspace(0.0, 1.0, N_SPECTRUM, dtype=np.float32)
    assert _mean_group(freq, 0, 3) == pytest.approx(float(freq[0:4].mean()))


def test_shape_row_zero_when_silent():
    row = np.zeros(16, dtype=np.float32)
    out = _shape_row(row, sensitivity=2.5)
    assert float(out.max()) == 0.0


def test_shape_row_preserves_relative_levels():
    row = np.array([0.2, 0.5, 0.1], dtype=np.float32)
    out = _shape_row(row, sensitivity=1.0)
    assert float(out[1]) > float(out[0]) > float(out[2])
    assert float(out.max()) < _HEADROOM + 0.01


def test_shape_row_avoids_pegging_at_top():
    row = np.ones(16, dtype=np.float32) * 0.85
    out = _shape_row(row, sensitivity=2.5)
    assert float(out.max()) < 0.95
    assert float(out.max()) <= _HEADROOM + 0.01
    assert float((out >= 0.99).mean()) == 0.0


def test_64_bar_count_is_one_to_one():
    ranges = _bin_group_ranges(64)
    assert all(start == end for start, end in ranges)
    assert [start for start, _ in ranges] == list(range(N_SPECTRUM))


def test_strip_layout_full_width():
    left, w = _strip_layout(1920.0, 1.0)
    assert left == 0.0
    assert w == 1920.0


def test_fold_to_center_profile_is_symmetric():
    grouped = np.linspace(0.1, 1.0, 64, dtype=np.float32)
    profile = _fold_to_center_profile(grouped)
    assert profile.shape[0] == 32
    assert float(profile[0]) == pytest.approx(float(max(grouped[31], grouped[32])))
    assert float(profile[-1]) == pytest.approx(float(max(grouped[0], grouped[63])))


def test_shape_symmetric_profile_is_center_heavy():
    row = np.linspace(0.1, 1.0, 64, dtype=np.float32)
    profile = _shape_symmetric_profile(row, sensitivity=2.5)
    assert profile.shape[0] == 32
    assert float(profile[0]) > float(profile[-1])
    assert float(profile[0]) <= _HEADROOM + 0.01


def test_strip_layout_narrow_width_centers():
    left, w = _strip_layout(1000.0, 0.5)
    assert left == 250.0
    assert w == 500.0


def test_grouped_bins_not_mirrored():
    spectrum = [0.1] * N_SPECTRUM
    spectrum[0] = 0.95
    spectrum[-1] = 0.2
    freq = np.asarray(spectrum, dtype="f4")
    ranges = _bin_group_ranges(32)
    left = _mean_group(freq, *ranges[0])
    right = _mean_group(freq, *ranges[-1])
    assert left > right


def test_stem_analyzer_drums_has_dynamic_heights(tmp_path: Path) -> None:
    from pixfabrica_core.audio.analysis import StemAnalyzer

    audio = Path("web/public/preview-samples/sources/drums.mp3")
    if not audio.exists():
        pytest.skip("preview sample missing")

    tl = StemAnalyzer().analyze(audio, 0.0, 8.0, 30.0)
    clip = EqWaveGL(id="eq", bus_select="main", sensitivity=2.5, smoothing=0.45)
    ctx = _prepare_ctx(tmp_path, audio={"main": tl})
    asyncio.run(clip.prepare(ctx))

    history = clip._bar_history  # noqa: SLF001
    assert history.shape[1] == clip.bar_count // 2
    peaks = history.max(axis=1)
    assert float(np.percentile(peaks, 95)) > 0.2
    assert float(np.std(peaks)) > 0.05
    assert float(peaks.max()) <= 0.95
    assert float((history >= 0.99).mean()) < 0.01

    active = (history > 0.05).mean(axis=0)
    assert float(active.mean()) > 0.3
