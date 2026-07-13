"""Unit tests for boomerang duration planning."""

from __future__ import annotations

import pytest

from pixfabrica_api.video_boomerang import (
    compute_boomerang_plan,
    is_boomerang_derivative_path,
    reject_boomerang_derivative_source,
)
from pixfabrica_api.video_transcode import VideoTranscodeError


def test_boomerang_tiles_cycles_to_fill_job() -> None:
    plan = compute_boomerang_plan(
        source_duration=10.0,
        start_offset=0.0,
        playback_rate=1.0,
        max_duration=30.0,
        fps=24.0,
    )
    assert plan.capped is False
    assert plan.cycles == 2
    assert plan.output_duration == pytest.approx(40.0)
    assert plan.leg_source_seconds == pytest.approx(10.0)


def test_boomerang_tiles_short_clip() -> None:
    plan = compute_boomerang_plan(
        source_duration=7.0,
        start_offset=0.0,
        playback_rate=1.0,
        max_duration=30.0,
        fps=24.0,
    )
    assert plan.capped is False
    assert plan.cycles == 3
    assert plan.output_duration == pytest.approx(42.0)
    assert plan.leg_source_seconds == pytest.approx(7.0)


def test_boomerang_compressed_to_job_budget() -> None:
    plan = compute_boomerang_plan(
        source_duration=18.06,
        start_offset=0.0,
        playback_rate=1.0,
        max_duration=30.0,
        fps=24.0,
    )
    assert plan.capped is True
    assert plan.cycles == 1
    assert plan.output_duration == pytest.approx(30.0)
    assert plan.leg_source_seconds == pytest.approx(15.0)


def test_boomerang_respects_start_offset_and_rate() -> None:
    plan = compute_boomerang_plan(
        source_duration=20.0,
        start_offset=5.0,
        playback_rate=2.0,
        max_duration=30.0,
        fps=24.0,
    )
    assert plan.capped is False
    assert plan.cycles == 2
    assert plan.output_duration == pytest.approx(30.0)
    assert plan.leg_source_seconds == pytest.approx(15.0)


def test_is_boomerang_derivative_path() -> None:
    assert is_boomerang_derivative_path("clip.boomerang-abc123.mp4")
    assert is_boomerang_derivative_path("/media/clip.boomerang-abc123.mp4")
    assert is_boomerang_derivative_path("clip.boomerang-abc.boomerang-def.mp4")
    assert not is_boomerang_derivative_path("clip.mp4")
    assert not is_boomerang_derivative_path("boomerang-clip.mp4")


def test_reject_boomerang_derivative_source() -> None:
    with pytest.raises(VideoTranscodeError, match="already a boomerang derivative"):
        reject_boomerang_derivative_source("clip.boomerang-abc123.mp4")
    reject_boomerang_derivative_source("clip.mp4")
