"""Tests for Bad Signal burst envelope precomputation."""

from __future__ import annotations

import numpy as np
import pytest

from pixfabrica_core.audio.bus import AudioBusFrame
from pixfabrica_std_effects.effects._signal_envelope import (
    DECAY_ENVELOPE,
    band_height_px,
    merge_burst_layers,
    precompute_audio_bursts,
    precompute_procedural_bursts,
    precompute_signal_envelope,
)


def _frame(**kwargs: object) -> AudioBusFrame:
    base = AudioBusFrame.zero()
    return base.model_copy(update=kwargs)


def test_procedural_burst_applies_decay_envelope() -> None:
    intensity, _, _ = precompute_procedural_bursts(
        total_frames=30,
        fps=30.0,
        clip_id="signal-1",
        seed=42,
    )
    assert intensity.max() == DECAY_ENVELOPE[0]
    hit = int(intensity.argmax())
    assert intensity[hit : hit + len(DECAY_ENVELOPE)] == pytest.approx(list(DECAY_ENVELOPE))


def test_audio_burst_maps_clip_start_to_local_index() -> None:
    frames = [_frame(onset=False, amplitude=0.4) for _ in range(20)]
    frames[7] = _frame(onset=True, amplitude=0.9)

    intensity, _, _ = precompute_audio_bursts(
        total_frames=5,
        clip_start_frame=5,
        clip_id="signal-2",
        seed=7,
        sensitivity=0.0,
        bus_frames=frames,
    )

    assert intensity[2] == DECAY_ENVELOPE[0]
    assert intensity[3] == DECAY_ENVELOPE[1]


def test_merge_layers_takes_max_intensity() -> None:
    proc = (
        np.asarray([0.25, 0.0, 0.6], dtype=np.float32),
        np.asarray([1.0, 0.0, 2.0], dtype=np.float32),
        np.asarray([1.0, 1.0, -1.0], dtype=np.float32),
    )
    audio = (
        np.asarray([0.1, 0.8, 0.4], dtype=np.float32),
        np.asarray([3.0, 4.0, 5.0], dtype=np.float32),
        np.asarray([1.0, -1.0, 1.0], dtype=np.float32),
    )
    intensity, seed, sign = merge_burst_layers(proc, audio)
    assert intensity.tolist() == pytest.approx([0.25, 0.8, 0.6])
    assert seed.tolist() == [1.0, 4.0, 2.0]
    assert sign.tolist() == [1.0, -1.0, -1.0]


def test_hybrid_envelope_includes_both_layers() -> None:
    frames = [_frame(onset=False, amplitude=0.2) for _ in range(60)]
    frames[10] = _frame(onset=True, amplitude=0.95)

    merged = precompute_signal_envelope(
        total_frames=30,
        fps=30.0,
        clip_start_frame=0,
        clip_id="signal-3",
        seed=99,
        sensitivity=0.0,
        bus_select="main",
        bus_frames=frames,
    )
    procedural = precompute_procedural_bursts(
        total_frames=30,
        fps=30.0,
        clip_id="signal-3",
        seed=99,
    )
    audio = precompute_audio_bursts(
        total_frames=30,
        clip_start_frame=0,
        clip_id="signal-3",
        seed=99,
        sensitivity=0.0,
        bus_frames=frames,
    )

    assert merged[0].max() >= procedural[0].max()
    assert merged[0][10] == DECAY_ENVELOPE[0]
    assert audio[0][10] == DECAY_ENVELOPE[0]


def test_sensitivity_filters_quiet_onsets() -> None:
    frames = [_frame(onset=True, amplitude=0.05) for _ in range(6)]
    intensity, _, _ = precompute_audio_bursts(
        total_frames=6,
        clip_start_frame=0,
        clip_id="signal-4",
        seed=1,
        sensitivity=0.5,
        bus_frames=frames,
    )
    assert intensity.max() == 0.0


def test_no_bus_returns_procedural_only() -> None:
    intensity, _, _ = precompute_signal_envelope(
        total_frames=20,
        fps=30.0,
        clip_start_frame=0,
        clip_id="signal-5",
        seed=11,
        sensitivity=0.0,
        bus_select=None,
        bus_frames=None,
    )
    proc, _, _ = precompute_procedural_bursts(
        total_frames=20,
        fps=30.0,
        clip_id="signal-5",
        seed=11,
    )
    assert intensity.tolist() == proc.tolist()


def test_band_height_adaptive() -> None:
    assert band_height_px(200.0) == 12.0
    assert band_height_px(300.0) == 12.0
    assert band_height_px(301.0) == 24.0
