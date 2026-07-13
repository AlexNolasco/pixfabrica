"""Tests for camera-shake transform math."""

from __future__ import annotations

from pixfabrica_core.random import SeededRandom
from pixfabrica_std_effects._simplex import Simplex2D
from pixfabrica_std_effects.effects.shake_skia import ShakeTransform, compute_shake_transform


def _transform(*, time_s: float, time_origin_s: float, seed: int = 99) -> ShakeTransform:
    simplex = Simplex2D(SeededRandom(seed))
    return compute_shake_transform(
        simplex=simplex,
        time_s=time_s,
        time_origin_s=time_origin_s,
        width=1920.0,
        height=1080.0,
        intensity=0.015,
        rotation=2.0,
        frequency=1.5,
    )


def test_shake_zero_at_origin():
    t = _transform(time_s=3.0, time_origin_s=3.0)
    assert t.is_identity()


def test_shake_moves_after_origin():
    t = _transform(time_s=4.0, time_origin_s=3.0)
    assert not t.is_identity()


def test_shake_zero_intensity_and_rotation_is_identity():
    simplex = Simplex2D(SeededRandom(7))
    t = compute_shake_transform(
        simplex=simplex,
        time_s=10.0,
        time_origin_s=0.0,
        width=800.0,
        height=600.0,
        intensity=0.0,
        rotation=0.0,
        frequency=1.5,
    )
    assert t.is_identity()
