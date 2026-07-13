"""Tests for deterministic 2D simplex noise."""

from __future__ import annotations

from pixfabrica_core.random import SeededRandom
from pixfabrica_std_effects._simplex import Simplex2D


def test_simplex_same_seed_same_output():
    a = Simplex2D(SeededRandom(42))
    b = Simplex2D(SeededRandom(42))
    assert a.noise2d(1.25, 2.5) == b.noise2d(1.25, 2.5)
    assert a.noise2d(0.0, 0.0) == b.noise2d(0.0, 0.0)


def test_simplex_different_seeds_differ():
    a = Simplex2D(SeededRandom(1))
    b = Simplex2D(SeededRandom(2))
    assert a.noise2d(3.0, 4.0) != b.noise2d(3.0, 4.0)


def test_simplex_output_bounded():
    simplex = Simplex2D(SeededRandom.from_string("shake-test"))
    samples = [simplex.noise2d(x * 0.17, x * 0.31) for x in range(200)]
    assert all(-120.0 <= v <= 120.0 for v in samples)
