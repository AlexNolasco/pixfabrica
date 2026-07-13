"""Tests for std-time-counter and counter time formatting."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from pixfabrica_core.clips import JobInfo, RenderContext, TimeState
from pixfabrica_core.graphics import Rect
from pixfabrica_core.theme.color import ColorPalette
from pixfabrica_core.theme.typography import FontPalette
from pixfabrica_std.image.image_layout import compute_text_draw_rect
from pixfabrica_std.progress._progress_common import (
    counter_display_seconds,
    format_counter_time,
)
from pixfabrica_std.progress.time_counter import TimeCounter


def test_format_counter_time_mm_ss_zero_pads() -> None:
    assert format_counter_time(8.0, "mm:ss") == "00:08"
    assert format_counter_time(189.0, "mm:ss") == "03:09"


def test_format_counter_time_mm_ss_allows_large_minutes() -> None:
    assert format_counter_time(5400.0, "mm:ss") == "90:00"


def test_format_counter_time_h_mm_ss() -> None:
    assert format_counter_time(5.0, "h:mm:ss") == "0:00:05"
    assert format_counter_time(3661.0, "h:mm:ss") == "1:01:01"


def test_counter_display_seconds_forward_and_backward() -> None:
    assert counter_display_seconds(15.0, 60.0, "forward") == pytest.approx(15.0)
    assert counter_display_seconds(15.0, 60.0, "backward") == pytest.approx(45.0)


def test_compute_text_draw_rect_centered() -> None:
    x, y, draw_w, draw_h = compute_text_draw_rect(
        Rect(0, 0, 1000, 500),
        text_w=120.0,
        text_h=24.0,
        offset_x=0.5,
        offset_y=0.5,
        align="center",
    )
    assert draw_w == pytest.approx(120.0)
    assert draw_h == pytest.approx(24.0)
    assert x == pytest.approx(440.0)
    assert y == pytest.approx(238.0)


def test_compute_text_draw_rect_top_trailing() -> None:
    x, y, draw_w, draw_h = compute_text_draw_rect(
        Rect(0, 0, 1000, 500),
        text_w=80.0,
        text_h=20.0,
        offset_x=1.0,
        offset_y=0.0,
        align="topTrailing",
    )
    assert draw_w == pytest.approx(80.0)
    assert draw_h == pytest.approx(20.0)
    assert x == pytest.approx(920.0)
    assert y == pytest.approx(0.0)


def _draw_ctx(*, t: float, **clip_kwargs: Any) -> MagicMock:
    job = JobInfo(
        title="t",
        description="d",
        width=1000,
        height=500,
        fps=30.0,
        duration=120.0,
        colors=ColorPalette(),
        typography=FontPalette(),
        locale="en",
    )
    bounds = Rect(0, 0, 1000, 500)
    ctx = RenderContext(
        job=job,
        time=TimeState(t=t, frame=0),
        bounds=bounds,
        canvas=MagicMock(),
    )
    TimeCounter(id="tc", **clip_kwargs).draw(ctx)
    return ctx.canvas


def test_time_counter_draws_elapsed_in_clip_mode() -> None:
    canvas = _draw_ctx(
        t=25.0,
        start=10.0,
        duration=30.0,
        time_mode="clip",
        direction="forward",
        time_format="mm:ss",
    )
    canvas.drawString.assert_called_once()
    text = canvas.drawString.call_args[0][0]
    assert text == "00:15"


def test_time_counter_draws_remaining_in_clip_mode() -> None:
    canvas = _draw_ctx(
        t=25.0,
        start=10.0,
        duration=30.0,
        time_mode="clip",
        direction="backward",
        time_format="mm:ss",
    )
    text = canvas.drawString.call_args[0][0]
    assert text == "00:15"


def test_time_counter_job_mode_elapsed() -> None:
    canvas = _draw_ctx(
        t=25.0,
        start=10.0,
        duration=30.0,
        time_mode="job",
        direction="forward",
        time_format="mm:ss",
    )
    text = canvas.drawString.call_args[0][0]
    assert text == "00:25"


def test_time_counter_job_mode_remaining_h_format() -> None:
    canvas = _draw_ctx(
        t=25.0,
        start=10.0,
        duration=30.0,
        time_mode="job",
        direction="backward",
        time_format="h:mm:ss",
    )
    text = canvas.drawString.call_args[0][0]
    assert text == "0:01:35"
