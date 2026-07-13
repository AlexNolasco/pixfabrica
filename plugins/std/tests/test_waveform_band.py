"""Tests for std-waveform-band spectrum mapping, temporal smoothing, and band tilt."""

from __future__ import annotations

import asyncio
import math
from pathlib import Path

import numpy as np
import pytest

from pixfabrica_core.audio.bus import N_SPECTRUM, AudioBusFrame
from pixfabrica_core.clips import JobInfo, PrepareContext
from pixfabrica_core.theme.color import ColorPalette
from pixfabrica_core.theme.typography import FontPalette
from pixfabrica_std.audio.waveform_band import WaveformBand


def _clip_with_band(w: int = 100) -> WaveformBand:
    clip = WaveformBand(id="test", bin_start=0)
    clip._canvas_w = float(w)  # noqa: SLF001
    clip._skew_px = 0.0  # noqa: SLF001
    clip._nx = 0.0  # noqa: SLF001
    clip._ny = 1.0  # noqa: SLF001
    clip._band_top_l = 40.0  # noqa: SLF001
    clip._band_bot_l = 60.0  # noqa: SLF001
    clip._wave_amp = 8.5  # noqa: SLF001
    return clip


def _prepare_ctx(
    tmp_path: Path,
    *,
    width: int = 640,
    height: int = 480,
    audio: dict | None = None,
) -> PrepareContext:
    ji = JobInfo(
        title="t",
        description="d",
        width=width,
        height=height,
        fps=30.0,
        duration=2 / 30.0,
        colors=ColorPalette(),
        typography=FontPalette(),
        locale="en",
    )
    td = tmp_path / "temp"
    cd = tmp_path / "cache"
    td.mkdir(exist_ok=True)
    cd.mkdir(exist_ok=True)
    return PrepareContext(job=ji, temp_dir=td, cache_dir=cd, audio=audio or {})


def _prepared_clip(tmp_path: Path, *, angle: float = 0.0, width: int = 100) -> WaveformBand:
    clip = WaveformBand(
        id="test",
        angle=angle,
        offset_y=0.5,
        band_height=0.2,
        wave_freq=1.0,
        sensitivity=5.0,
        bin_start=0,
    )
    ctx = _prepare_ctx(tmp_path, width=width, height=200)
    asyncio.run(clip.prepare(ctx))
    return clip


def test_symmetric_mapping_peaks_at_center_for_low_bins():
    clip = _clip_with_band(100)
    data = np.zeros(N_SPECTRUM, dtype=np.float32)
    data[0] = 1.0
    _wave_x, wave_y = clip._compute_wave_xy(data)  # noqa: SLF001
    center = 50
    assert wave_y[center] > wave_y[0]
    assert wave_y[center] > wave_y[100]


def test_bin_start_skips_sub_bass_at_center():
    clip = _clip_with_band(100)
    clip.bin_start = 10
    only_sub = np.zeros(N_SPECTRUM, dtype=np.float32)
    only_sub[0] = 1.0
    low_only = clip._compute_wave_xy(only_sub)[1]  # noqa: SLF001

    with_ten = np.zeros(N_SPECTRUM, dtype=np.float32)
    with_ten[10] = 1.0
    at_bin_ten = clip._compute_wave_xy(with_ten)[1]  # noqa: SLF001

    assert abs(at_bin_ten[50] - 50.0) > abs(low_only[50] - 50.0)


def test_smoothing_timeline_retains_previous_energy(tmp_path: Path) -> None:
    clip = WaveformBand(id="test", smoothing=0.85, bus_select="main")
    frames = [
        AudioBusFrame(
            spectrum=[1.0] + [0.0] * (N_SPECTRUM - 1),
            bass=0.0,
            mid=0.0,
            high=0.0,
            beat=False,
            amplitude=1.0,
        ),
        AudioBusFrame.zero(),
    ]
    ctx = _prepare_ctx(tmp_path, audio={"main": frames})
    history = clip._build_smoothed_timeline(ctx)  # noqa: SLF001
    assert history.shape == (2, N_SPECTRUM)
    # First frame: EMA from zero → 1.0 * (1 - smoothing)
    assert history[0, 0] == pytest.approx(0.15)
    # Second frame: decays toward zero when bus is silent
    assert history[1, 0] == pytest.approx(0.15 * 0.85)


def _displacement_at(
    clip: WaveformBand,
    data: np.ndarray,
    x: int,
    *,
    amplitude: float = 1.0,
) -> float:
    wave_x, wave_y = clip._compute_wave_xy(data, amplitude=amplitude)  # noqa: SLF001
    xs = float(x)
    band_mid = (clip._band_top_l + clip._band_bot_l) * 0.5  # noqa: SLF001
    skew_per_x = clip._skew_px / clip._canvas_w if clip._canvas_w > 0 else 0.0  # noqa: SLF001
    base_y = band_mid - skew_per_x * xs
    disp_y = float(wave_y[x] - base_y)
    disp_x = float(wave_x[x] - xs)
    return math.hypot(disp_x, disp_y)


def _peak_displacement(
    clip: WaveformBand,
    data: np.ndarray,
    *,
    amplitude: float = 1.0,
) -> float:
    wave_x, wave_y = clip._compute_wave_xy(data, amplitude=amplitude)  # noqa: SLF001
    xs = np.arange(clip._canvas_w + 1, dtype=np.float32)  # noqa: SLF001
    band_mid = (clip._band_top_l + clip._band_bot_l) * 0.5  # noqa: SLF001
    skew_per_x = clip._skew_px / clip._canvas_w if clip._canvas_w > 0 else 0.0  # noqa: SLF001
    base_y = band_mid - skew_per_x * xs
    disp_y = wave_y - base_y
    disp_x = wave_x - xs
    return float(np.max(np.hypot(disp_x, disp_y)))


def test_zero_angle_displacement_is_vertical_only():
    clip = _clip_with_band(100)
    data = np.zeros(N_SPECTRUM, dtype=np.float32)
    data[0] = 1.0
    wave_x, _wave_y = clip._compute_wave_xy(data)  # noqa: SLF001
    xs = np.arange(101, dtype=np.float32)
    assert np.allclose(wave_x, xs)


def test_tilted_displacement_follows_band_normal(tmp_path: Path) -> None:
    clip = _prepared_clip(tmp_path, angle=45.0, width=100)
    data = np.zeros(N_SPECTRUM, dtype=np.float32)
    data[0] = 1.0
    wave_x, wave_y = clip._compute_wave_xy(data)  # noqa: SLF001
    center = 50
    xs = np.arange(101, dtype=np.float32)
    band_mid = (clip._band_top_l + clip._band_bot_l) * 0.5  # noqa: SLF001
    skew_per_x = clip._skew_px / clip._canvas_w  # noqa: SLF001
    base_y = band_mid - skew_per_x * xs
    disp_x = float(wave_x[center] - xs[center])
    disp_y = float(wave_y[center] - base_y[center])
    assert abs(disp_x) == pytest.approx(abs(disp_y), rel=1e-4)
    peak_mag = math.hypot(disp_x, disp_y)
    assert peak_mag == pytest.approx(clip._wave_amp, rel=1e-4)  # noqa: SLF001


def test_tilted_amplitude_scales_with_cos_band_angle(tmp_path: Path) -> None:
    flat = _prepared_clip(tmp_path, angle=0.0, width=100)
    tilted = _prepared_clip(tmp_path, angle=45.0, width=100)
    data = np.zeros(N_SPECTRUM, dtype=np.float32)
    data[0] = 1.0

    flat_peak = _peak_displacement(flat, data)
    tilted_peak = _peak_displacement(tilted, data)
    expected_scale = math.cos(math.radians(45.0))

    assert flat_peak > tilted_peak
    assert tilted_peak == pytest.approx(flat_peak * expected_scale, rel=1e-4)


def test_focus_one_preserves_linear_spread():
    clip = _clip_with_band(100)
    data = np.zeros(N_SPECTRUM, dtype=np.float32)
    data[0] = 1.0
    clip.focus = 1.0
    quarter = _displacement_at(clip, data, 25)
    three_quarter = _displacement_at(clip, data, 75)
    assert quarter == pytest.approx(three_quarter, rel=1e-4)


def test_focus_center_unchanged():
    clip = _clip_with_band(100)
    data = np.zeros(N_SPECTRUM, dtype=np.float32)
    data[0] = 1.0
    clip.focus = 1.0
    loose_center = _displacement_at(clip, data, 50)

    clip.focus = 4.0
    tight_center = _displacement_at(clip, data, 50)

    assert tight_center == pytest.approx(loose_center, rel=1e-4)


def test_focus_squeezes_midpoint_toward_center():
    clip = _clip_with_band(100)
    clip.wave_freq = 1.0
    data = np.ones(N_SPECTRUM, dtype=np.float32)

    clip.focus = 1.0
    loose_quarter = _displacement_at(clip, data, 25)

    clip.focus = 4.0
    tight_quarter = _displacement_at(clip, data, 25)

    assert tight_quarter < loose_quarter
    assert tight_quarter > 0.0


def test_focus_calms_edges():
    clip = _clip_with_band(100)
    data = np.zeros(N_SPECTRUM, dtype=np.float32)
    data[-1] = 1.0

    clip.focus = 1.0
    loose_edge = _displacement_at(clip, data, 0)

    clip.focus = 4.0
    tight_edge = _displacement_at(clip, data, 0)

    assert loose_edge > 0.0
    assert tight_edge == pytest.approx(0.0, abs=1e-4)


def test_stem_analyzer_drums_bus_has_visible_displacement(tmp_path: Path) -> None:
    """Regression: StemAnalyzer spectrum must drive visible motion (not tanh-squared flat)."""
    from pixfabrica_core.audio.analysis import StemAnalyzer

    audio = Path("web/public/preview-samples/sources/drums.mp3")
    if not audio.exists():
        pytest.skip("preview sample missing")

    tl = StemAnalyzer().analyze(audio, 0.0, 8.0, 30.0)
    clip = WaveformBand(id="wb", bus_select="main", sensitivity=2.0, smoothing=0.0)
    ctx = _prepare_ctx(tmp_path, audio={"main": tl})
    asyncio.run(clip.prepare(ctx))

    peaks = [
        _peak_displacement(
            clip, np.asarray(frame.spectrum, dtype=np.float32), amplitude=float(frame.amplitude)
        )
        for frame in tl
    ]
    assert max(peaks) > 0.05
    assert float(np.percentile(peaks, 95)) > 0.02
