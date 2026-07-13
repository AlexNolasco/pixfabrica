"""Tests for lyrics word cloud helpers."""

from __future__ import annotations

from typing import Literal

import skia

from pixfabrica_core.lyrics import CaptionSegment
from pixfabrica_std.text.word_cloud import (
    _build_word_counts,
    _drift_axes,
    _drift_region,
    _normalize_token,
    _simulate_trajectories,
    _WordLayout,
)


def test_normalize_token_strips_punctuation_and_lowercases() -> None:
    assert _normalize_token("Life,") == "life"
    assert _normalize_token("ROSES") == "roses"
    assert _normalize_token("---") is None


def test_build_word_counts_filters_and_ranks() -> None:
    segments = [
        CaptionSegment(index=0, start=0.0, end=1.0, text="Red like roses, red roses"),
        CaptionSegment(index=1, start=1.0, end=2.0, text="roses fill my head"),
    ]
    ranked = _build_word_counts(segments, min_count=2, max_words=10)
    assert ranked[0] == ("roses", 3)
    assert ("red", 2) in ranked
    assert all(count >= 2 for _, count in ranked)


def test_simulate_trajectories_is_deterministic() -> None:
    font = skia.Font(None, 24)
    metrics = font.getMetrics()
    layouts = [
        _WordLayout(
            text="roses",
            count=3,
            ratio=1.0,
            speed=60.0,
            font=font,
            width=font.measureText("roses"),
            ascent=metrics.fAscent,
        ),
        _WordLayout(
            text="red",
            count=2,
            ratio=0.66,
            speed=40.0,
            font=font,
            width=font.measureText("red"),
            ascent=metrics.fAscent,
        ),
    ]
    region = _drift_region(1920.0, 1080.0, 0.05, 0.5, 0.5)
    xs1, ys1 = _simulate_trajectories(
        layouts,
        direction="right",
        angle=0.0,
        region_left=region[0],
        region_top=region[1],
        region_w=region[2],
        region_h=region[3],
        fps=30.0,
        total_frames=120,
        clip_id="clip-1",
        seed=42,
    )
    xs2, ys2 = _simulate_trajectories(
        layouts,
        direction="right",
        angle=0.0,
        region_left=region[0],
        region_top=region[1],
        region_w=region[2],
        region_h=region[3],
        fps=30.0,
        total_frames=120,
        clip_id="clip-1",
        seed=42,
    )
    assert (xs1 == xs2).all()
    assert (ys1 == ys2).all()
    assert xs1.shape == (120, 2)


def test_drift_axes_follow_angle_when_tilted() -> None:
    drift_right, cross = _drift_axes("right", 45.0)
    drift_left, cross_left = _drift_axes("left", 45.0)
    assert drift_right == drift_left
    assert cross == cross_left
    assert drift_right[0] > 0.0
    assert drift_right[1] > 0.0
    assert abs(drift_right[0] - drift_right[1]) < 1e-6


def test_simulate_trajectories_at_angle_moves_diagonally() -> None:
    font = skia.Font(None, 24)
    metrics = font.getMetrics()
    layouts = [
        _WordLayout(
            text="roses",
            count=3,
            ratio=1.0,
            speed=60.0,
            font=font,
            width=font.measureText("roses"),
            ascent=metrics.fAscent,
        ),
    ]
    region = _drift_region(1920.0, 1080.0, 0.05, 0.5, 0.5)
    xs, ys = _simulate_trajectories(
        layouts,
        direction="right",
        angle=45.0,
        region_left=region[0],
        region_top=region[1],
        region_w=region[2],
        region_h=region[3],
        fps=30.0,
        total_frames=2,
        clip_id="clip-1",
        seed=42,
    )
    dx = float(xs[1, 0] - xs[0, 0])
    dy = float(ys[1, 0] - ys[0, 0])
    assert dx > 0.0
    assert dy > 0.0
    assert abs(dx - dy) < 1e-3


def test_simulate_trajectories_left_reverses_oriented_drift() -> None:
    font = skia.Font(None, 24)
    metrics = font.getMetrics()
    layouts = [
        _WordLayout(
            text="roses",
            count=3,
            ratio=1.0,
            speed=60.0,
            font=font,
            width=font.measureText("roses"),
            ascent=metrics.fAscent,
        ),
    ]
    region = _drift_region(1920.0, 1080.0, 0.05, 0.5, 0.5)

    def run(direction: Literal["left", "right"]):
        return _simulate_trajectories(
            layouts,
            direction=direction,
            angle=45.0,
            region_left=region[0],
            region_top=region[1],
            region_w=region[2],
            region_h=region[3],
            fps=30.0,
            total_frames=2,
            clip_id="clip-1",
            seed=42,
        )

    xs_r, ys_r = run("right")
    xs_l, ys_l = run("left")
    dx_r = float(xs_r[1, 0] - xs_r[0, 0])
    dy_r = float(ys_r[1, 0] - ys_r[0, 0])
    dx_l = float(xs_l[1, 0] - xs_l[0, 0])
    dy_l = float(ys_l[1, 0] - ys_l[0, 0])
    assert dx_r > 0.0 and dy_r > 0.0
    assert dx_l < 0.0 and dy_l < 0.0
    assert abs(dx_r + dx_l) < 1e-3
    assert abs(dy_r + dy_l) < 1e-3
