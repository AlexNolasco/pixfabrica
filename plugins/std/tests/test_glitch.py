"""Tests for std-glitch burst envelope precomputation."""

from __future__ import annotations

from pixfabrica_core.audio.bus import AudioBusFrame
from pixfabrica_std.effects.glitch import DECAY_ENVELOPE, precompute_glitch_envelope


def _frame(**kwargs: object) -> AudioBusFrame:
    base = AudioBusFrame.zero()
    return base.model_copy(update=kwargs)


def test_onset_applies_four_frame_exponential_decay() -> None:
    frames = [_frame(onset=False, amplitude=0.5) for _ in range(10)]
    frames[3] = _frame(onset=True, amplitude=0.8)

    intensity, _, _ = precompute_glitch_envelope(
        total_frames=10,
        fps=30.0,
        clip_id="glitch-1",
        seed=42,
        sensitivity=0.0,
        bus_select="main",
        bus_frames=frames,
    )

    assert intensity[3] == DECAY_ENVELOPE[0]
    assert intensity[4] == DECAY_ENVELOPE[1]
    assert intensity[5] == DECAY_ENVELOPE[2]
    assert intensity[6] == DECAY_ENVELOPE[3]
    assert intensity[7] == 0.0


def test_sensitivity_filters_quiet_onsets() -> None:
    frames = [_frame(onset=True, amplitude=0.05) for _ in range(6)]

    intensity, _, _ = precompute_glitch_envelope(
        total_frames=6,
        fps=30.0,
        clip_id="glitch-2",
        seed=7,
        sensitivity=0.5,
        bus_select="main",
        bus_frames=frames,
    )

    assert intensity.max() == 0.0


def test_no_bus_uses_seeded_random_fallback() -> None:
    intensity_a, _, _ = precompute_glitch_envelope(
        total_frames=300,
        fps=30.0,
        clip_id="glitch-3",
        seed=99,
        sensitivity=0.0,
        bus_select=None,
        bus_frames=None,
    )
    intensity_b, _, _ = precompute_glitch_envelope(
        total_frames=300,
        fps=30.0,
        clip_id="glitch-3",
        seed=99,
        sensitivity=0.0,
        bus_select=None,
        bus_frames=None,
    )
    intensity_other, _, _ = precompute_glitch_envelope(
        total_frames=300,
        fps=30.0,
        clip_id="glitch-3",
        seed=100,
        sensitivity=0.0,
        bus_select=None,
        bus_frames=None,
    )

    assert (intensity_a == intensity_b).all()
    assert intensity_a.max() > 0.0
    assert not (intensity_a == intensity_other).all()


def test_bus_flat_amplitude_produces_no_bursts() -> None:
    intensity, _, _ = precompute_glitch_envelope(
        total_frames=300,
        fps=30.0,
        clip_id="glitch-4",
        seed=99,
        sensitivity=0.0,
        bus_select="main",
        bus_frames=[_frame(onset=False, amplitude=0.0) for _ in range(300)],
    )

    assert intensity.max() == 0.0


def test_amplitude_spike_fallback_triggers_burst() -> None:
    frames = [_frame(onset=False, amplitude=0.2) for _ in range(10)]
    frames[5] = _frame(onset=False, amplitude=0.5)

    intensity, _, _ = precompute_glitch_envelope(
        total_frames=10,
        fps=30.0,
        clip_id="glitch-6",
        seed=42,
        sensitivity=0.0,
        bus_select="main",
        bus_frames=frames,
    )

    assert intensity[5] == DECAY_ENVELOPE[0]
    assert intensity[6] == DECAY_ENVELOPE[1]


def test_amplitude_fallback_skips_during_active_decay() -> None:
    frames = [
        _frame(onset=False, amplitude=0.1),
        _frame(onset=False, amplitude=0.35),
        _frame(onset=False, amplitude=0.55),
        _frame(onset=False, amplitude=0.75),
        _frame(onset=False, amplitude=0.95),
        _frame(onset=False, amplitude=0.2),
        _frame(onset=False, amplitude=0.45),
    ]

    intensity, _, _ = precompute_glitch_envelope(
        total_frames=len(frames),
        fps=30.0,
        clip_id="glitch-7",
        seed=1,
        sensitivity=0.0,
        bus_select="main",
        bus_frames=frames,
    )

    assert intensity[1] == DECAY_ENVELOPE[0]
    assert intensity[2] == DECAY_ENVELOPE[1]
    assert intensity[6] == DECAY_ENVELOPE[0]


def test_amplitude_fallback_sensitivity_filters_quiet_spikes() -> None:
    frames = [_frame(onset=False, amplitude=0.05) for _ in range(4)]
    frames[3] = _frame(onset=False, amplitude=0.25)

    intensity, _, _ = precompute_glitch_envelope(
        total_frames=4,
        fps=30.0,
        clip_id="glitch-8",
        seed=1,
        sensitivity=1.0,
        bus_select="main",
        bus_frames=frames,
    )

    assert intensity.max() == 0.0


def test_onset_timeline_ignores_amplitude_spikes() -> None:
    frames = [_frame(onset=False, amplitude=0.2) for _ in range(6)]
    frames[2] = _frame(onset=True, amplitude=0.8)
    frames[4] = _frame(onset=False, amplitude=0.9)

    intensity, _, _ = precompute_glitch_envelope(
        total_frames=6,
        fps=30.0,
        clip_id="glitch-9",
        seed=1,
        sensitivity=0.0,
        bus_select="main",
        bus_frames=frames,
    )

    assert intensity[2] == DECAY_ENVELOPE[0]
    assert intensity[4] == DECAY_ENVELOPE[2]


def test_overlapping_bursts_keep_stronger_decay() -> None:
    frames = [_frame(onset=False, amplitude=0.9) for _ in range(8)]
    frames[2] = _frame(onset=True, amplitude=0.9)
    frames[4] = _frame(onset=True, amplitude=0.9)

    intensity, _, _ = precompute_glitch_envelope(
        total_frames=8,
        fps=30.0,
        clip_id="glitch-5",
        seed=1,
        sensitivity=0.0,
        bus_select="main",
        bus_frames=frames,
    )

    assert intensity[4] == DECAY_ENVELOPE[0]
    assert intensity[5] == DECAY_ENVELOPE[1]
