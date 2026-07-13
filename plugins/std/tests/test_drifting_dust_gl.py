"""Tests for std-drifting-dust-gl gust envelope precomputation."""

from __future__ import annotations

import math

import numpy as np

from pixfabrica_core.audio.bus import AudioBusFrame
from pixfabrica_std.particles.drifting_dust_gl import (
    _GUST_DECAY_K,
    precompute_dust_gust_envelope,
    precompute_dust_time_warp,
    scale_max_size_for_job,
)


def _frame(**kwargs: object) -> AudioBusFrame:
    base = AudioBusFrame.zero()
    return base.model_copy(update=kwargs)


def test_onset_stamps_exponential_gust_decay() -> None:
    frames = [_frame(onset=False, amplitude=0.5) for _ in range(20)]
    frames[5] = _frame(onset=True, amplitude=0.8)

    gust = precompute_dust_gust_envelope(
        total_frames=20,
        fps=30.0,
        clip_id="dust-1",
        seed=42,
        sensitivity=0.0,
        gust_duration=0.4,
        gust_boost=3.0,
        bus_select="main",
        bus_frames=frames,
    )

    duration_frames = max(1, int(0.4 * 30.0))
    assert gust[5] == 3.0
    mid_i = duration_frames // 2
    mid_age = float(mid_i) / float(max(1, duration_frames - 1))
    expected_mid = 1.0 + (3.0 - 1.0) * math.exp(-_GUST_DECAY_K * mid_age)
    assert gust[5 + mid_i] == expected_mid
    assert gust[5 + duration_frames - 1] > 1.0
    assert gust[5 + duration_frames - 1] < 1.05


def test_sensitivity_filters_quiet_onsets() -> None:
    frames = [_frame(onset=True, amplitude=0.05) for _ in range(6)]

    gust = precompute_dust_gust_envelope(
        total_frames=6,
        fps=30.0,
        clip_id="dust-2",
        seed=7,
        sensitivity=0.5,
        gust_duration=0.4,
        gust_boost=2.5,
        bus_select="main",
        bus_frames=frames,
    )

    assert gust.max() == 1.0


def test_no_bus_uses_seeded_random_fallback() -> None:
    gust_a = precompute_dust_gust_envelope(
        total_frames=300,
        fps=30.0,
        clip_id="dust-3",
        seed=99,
        sensitivity=0.0,
        gust_duration=0.4,
        gust_boost=2.5,
        bus_select=None,
        bus_frames=None,
    )
    gust_b = precompute_dust_gust_envelope(
        total_frames=300,
        fps=30.0,
        clip_id="dust-3",
        seed=99,
        sensitivity=0.0,
        gust_duration=0.4,
        gust_boost=2.5,
        bus_select=None,
        bus_frames=None,
    )
    gust_other = precompute_dust_gust_envelope(
        total_frames=300,
        fps=30.0,
        clip_id="dust-3",
        seed=100,
        sensitivity=0.0,
        gust_duration=0.4,
        gust_boost=2.5,
        bus_select=None,
        bus_frames=None,
    )

    assert (gust_a == gust_b).all()
    assert gust_a.max() > 1.0
    assert not (gust_a == gust_other).all()


def test_amplitude_spike_fallback_triggers_gust() -> None:
    frames = [_frame(onset=False, amplitude=0.2) for _ in range(10)]
    frames[4] = _frame(onset=False, amplitude=0.45)

    gust = precompute_dust_gust_envelope(
        total_frames=10,
        fps=30.0,
        clip_id="dust-4",
        seed=11,
        sensitivity=0.0,
        gust_duration=0.3,
        gust_boost=2.0,
        bus_select="main",
        bus_frames=frames,
    )

    assert gust[4] > 1.0


def test_time_warp_integrates_gust_multipliers() -> None:
    gust = np.array([1.0, 2.0, 2.0, 1.0], dtype="f4")
    warp = precompute_dust_time_warp(gust, fps=10.0, speed=1.0)

    assert warp[0] == 0.0
    assert warp[1] == 0.1
    assert warp[2] == 0.3
    assert warp[3] == 0.5


def test_scale_max_size_matches_frame_height_fraction() -> None:
    max_size = 12.0
    expected_fraction = max_size / 1080.0

    for height in (360, 1080, 2160):
        effective = scale_max_size_for_job(max_size, height)
        assert effective == max_size * (height / 1080.0)
        assert effective / height == expected_fraction


def test_scale_max_size_preview_matches_legacy_prominence() -> None:
    # Old preview: 4px at 360p. New WYSIWYG default: 12px ref -> 4px at 360p draw.
    assert scale_max_size_for_job(12.0, 360) == 4.0
