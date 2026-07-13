"""Tests for std-spectrum-glitch drive precomputation."""

from __future__ import annotations

import numpy as np

from pixfabrica_core.audio.bus import N_SPECTRUM, AudioBusFrame
from pixfabrica_std.effects.spectrum_glitch import (
    _JS_BOX_K,
    _JS_RGB_K,
    NORM_BOX_K,
    drives_from_level,
    level_avg_from_spectrum,
    precompute_spectrum_drives,
    self_ref_drive,
)


def _frame(**kwargs: object) -> AudioBusFrame:
    base = AudioBusFrame.zero()
    return base.model_copy(update=kwargs)


def test_level_avg_from_spectrum_mean() -> None:
    spec = [0.2] * N_SPECTRUM
    assert level_avg_from_spectrum(spec) == 0.2


def test_self_ref_drive_zero_when_silent() -> None:
    assert self_ref_drive(0.0, _JS_BOX_K) == 0.0


def test_self_ref_drive_matches_normalized_formula() -> None:
    level = 0.5
    ratio = min(level / NORM_BOX_K, 4.0)
    expected = ratio**ratio
    assert self_ref_drive(level, _JS_BOX_K) == expected


def test_rgb_drive_uses_lower_k_than_box() -> None:
    level = 0.6
    box, rgb = drives_from_level(level)
    assert rgb >= box
    assert self_ref_drive(level, _JS_RGB_K) == rgb


def test_no_bus_produces_zeros() -> None:
    level, box, rgb = precompute_spectrum_drives(
        total_frames=10,
        sensitivity=1.0,
        bus_select=None,
        bus_frames=None,
    )
    assert level.max() == 0.0
    assert box.max() == 0.0
    assert rgb.max() == 0.0


def test_empty_bus_select_produces_zeros() -> None:
    frames = [_frame(amplitude=0.9, spectrum=[1.0] * N_SPECTRUM) for _ in range(5)]
    level, box, rgb = precompute_spectrum_drives(
        total_frames=5,
        sensitivity=1.0,
        bus_select="  ",
        bus_frames=frames,
    )
    assert level.max() == 0.0


def test_loud_bus_frames_drive_nonzero() -> None:
    spec = [0.8] * N_SPECTRUM
    frames = [_frame(amplitude=0.8, spectrum=spec) for _ in range(4)]
    level, box, rgb = precompute_spectrum_drives(
        total_frames=4,
        sensitivity=1.0,
        bus_select="main",
        bus_frames=frames,
    )
    assert level[0] == 0.8
    assert box[0] > 0.0
    assert rgb[0] > 0.0
    assert rgb[0] >= box[0]


def test_sensitivity_scales_level() -> None:
    spec = [0.5] * N_SPECTRUM
    frames = [_frame(spectrum=spec)]
    level, _, _ = precompute_spectrum_drives(
        total_frames=1,
        sensitivity=2.0,
        bus_select="main",
        bus_frames=frames,
    )
    assert level[0] == 1.0


def test_silent_bus_stays_clean() -> None:
    frames = [_frame(amplitude=0.0, spectrum=[0.0] * N_SPECTRUM) for _ in range(6)]
    level, box, rgb = precompute_spectrum_drives(
        total_frames=6,
        sensitivity=1.0,
        bus_select="main",
        bus_frames=frames,
    )
    assert np.all(level == 0.0)
    assert np.all(box == 0.0)
    assert np.all(rgb == 0.0)


def test_precompute_respects_timeline_length() -> None:
    frames = [_frame(spectrum=[0.4] * N_SPECTRUM) for _ in range(3)]
    level, _, _ = precompute_spectrum_drives(
        total_frames=10,
        sensitivity=1.0,
        bus_select="main",
        bus_frames=frames,
    )
    assert level[2] == 0.4
    assert level[3] == 0.0
