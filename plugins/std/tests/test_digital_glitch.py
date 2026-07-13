"""Tests for std-digital-glitch scheduling and displacement map."""

from __future__ import annotations

import numpy as np

from pixfabrica_core.audio.bus import AudioBusFrame
from pixfabrica_core.random import SeededRandom
from pixfabrica_std.effects.digital_glitch import (
    DISP_MAP_SIZE,
    ONSET_MILD_TAIL_FRAMES,
    DigitalGlitchFrame,
    apply_bus_onset_stamps,
    generate_displacement_map,
    precompute_glitch_pass_frames,
)


def _frame(**kwargs: object) -> AudioBusFrame:
    base = AudioBusFrame.zero()
    return base.model_copy(update=kwargs)


def test_displacement_map_size_and_range() -> None:
    rng = SeededRandom(42)
    data = generate_displacement_map(DISP_MAP_SIZE, rng)
    assert data.shape == (DISP_MAP_SIZE, DISP_MAP_SIZE)
    assert data.min() >= 0.0
    assert data.max() < 1.0


def test_displacement_map_is_seeded() -> None:
    a = generate_displacement_map(8, SeededRandom(7))
    b = generate_displacement_map(8, SeededRandom(7))
    c = generate_displacement_map(8, SeededRandom(8))
    assert np.allclose(a, b)
    assert not np.allclose(a, c)


def test_first_frame_always_glitches_when_not_wild() -> None:
    frames = precompute_glitch_pass_frames(
        total_frames=5,
        clip_id="dg-1",
        seed=99,
        go_wild=False,
        strength=1.0,
    )
    assert not frames[0].bypass


def test_go_wild_never_bypasses() -> None:
    frames = precompute_glitch_pass_frames(
        total_frames=300,
        clip_id="dg-2",
        seed=1,
        go_wild=True,
        strength=1.0,
    )
    assert all(not frame.bypass for frame in frames)


def test_schedule_is_deterministic() -> None:
    kwargs = {
        "total_frames": 400,
        "clip_id": "dg-3",
        "seed": 12,
        "go_wild": False,
        "strength": 1.0,
    }
    a = precompute_glitch_pass_frames(**kwargs)
    b = precompute_glitch_pass_frames(**kwargs)
    assert [(f.bypass, round(f.amount, 6)) for f in a] == [
        (f.bypass, round(f.amount, 6)) for f in b
    ]


def test_strength_scales_amount() -> None:
    full = precompute_glitch_pass_frames(
        total_frames=1,
        clip_id="dg-4",
        seed=5,
        go_wild=True,
        strength=1.0,
    )
    half = precompute_glitch_pass_frames(
        total_frames=1,
        clip_id="dg-4",
        seed=5,
        go_wild=True,
        strength=0.5,
    )
    assert half[0].amount == full[0].amount * 0.5


def test_normal_schedule_has_clean_frames() -> None:
    frames = precompute_glitch_pass_frames(
        total_frames=500,
        clip_id="dg-5",
        seed=3,
        go_wild=False,
        strength=1.0,
    )
    assert any(frame.bypass for frame in frames)
    assert any(not frame.bypass for frame in frames)


def test_onset_stamps_full_and_mild_tail() -> None:
    base = [
        DigitalGlitchFrame(
            bypass=True,
            amount=0.0,
            angle=0.0,
            seed=0.0,
            seed_x=0.0,
            seed_y=0.0,
            distortion_x=0.0,
            distortion_y=0.0,
        )
        for _ in range(10)
    ]
    frames = [_frame(onset=False, amplitude=0.5) for _ in range(10)]
    frames[4] = _frame(onset=True, amplitude=0.8)

    stamped = apply_bus_onset_stamps(
        list(base),
        clip_id="dg-onset",
        seed=42,
        strength=1.0,
        sensitivity=1.0,
        bus_select="main",
        bus_frames=frames,
    )

    assert not stamped[4].bypass
    assert stamped[4].amount > 0.0
    for i in range(1, ONSET_MILD_TAIL_FRAMES):
        assert not stamped[4 + i].bypass


def test_onset_sensitivity_filters_quiet_hits() -> None:
    frames = [_frame(onset=True, amplitude=0.05) for _ in range(6)]
    base = precompute_glitch_pass_frames(
        total_frames=6,
        clip_id="dg-quiet",
        seed=1,
        go_wild=False,
        strength=1.0,
        sensitivity=1.0,
        bus_select="main",
        bus_frames=frames,
    )
    without_bus = precompute_glitch_pass_frames(
        total_frames=6,
        clip_id="dg-quiet",
        seed=1,
        go_wild=False,
        strength=1.0,
    )
    assert base == without_bus


def test_onset_merges_with_procedural_schedule() -> None:
    bus = [_frame(onset=False, amplitude=0.2) for _ in range(200)]
    bus[50] = _frame(onset=True, amplitude=0.9)

    merged = precompute_glitch_pass_frames(
        total_frames=200,
        clip_id="dg-merge",
        seed=7,
        go_wild=False,
        strength=1.0,
        sensitivity=0.0,
        bus_select="main",
        bus_frames=bus,
    )
    procedural = precompute_glitch_pass_frames(
        total_frames=200,
        clip_id="dg-merge",
        seed=7,
        go_wild=False,
        strength=1.0,
    )

    assert not merged[50].bypass
    assert merged[50] != procedural[50] or not procedural[50].bypass
