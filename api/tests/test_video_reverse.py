"""Unit tests for reverse duration planning."""

from __future__ import annotations

import pytest

from pixfabrica_api.video_reverse import compute_reverse_plan


def test_reverse_full_source() -> None:
    plan = compute_reverse_plan(
        source_duration=18.0,
        start_offset=0.0,
        playback_rate=1.0,
        fps=24.0,
    )
    assert plan.source_seconds == pytest.approx(18.0)
    assert plan.output_duration == pytest.approx(18.0)


def test_reverse_respects_start_offset_and_rate() -> None:
    plan = compute_reverse_plan(
        source_duration=20.0,
        start_offset=5.0,
        playback_rate=2.0,
        fps=24.0,
    )
    assert plan.source_seconds == pytest.approx(15.0)
    assert plan.output_duration == pytest.approx(7.5)
