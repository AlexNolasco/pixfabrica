"""Tests for std-circular-progress."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from pixfabrica_core.clips import JobInfo, RenderContext, TimeState
from pixfabrica_core.graphics import Rect
from pixfabrica_core.theme.color import ColorPalette
from pixfabrica_core.theme.typography import FontPalette
from pixfabrica_std.progress._progress_common import playback_times
from pixfabrica_std.progress.circular_progress import (
    CircularProgress,
    arc_sweep_deg,
    glow_blur_px,
    ring_geometry,
)


def test_ring_geometry_centered_default_size() -> None:
    geom = ring_geometry(Rect(0, 0, 1000, 500), offset_x=0.5, offset_y=0.5, size=0.2)
    assert geom is not None
    cx, cy, radius, min_dim = geom
    assert cx == pytest.approx(500.0)
    assert cy == pytest.approx(250.0)
    assert min_dim == pytest.approx(500.0)
    assert radius == pytest.approx(50.0)


def test_ring_geometry_zero_size_returns_none() -> None:
    assert ring_geometry(Rect(0, 0, 100, 80), offset_x=0.5, offset_y=0.5, size=0.0) is None


def test_glow_blur_px_clamps() -> None:
    assert glow_blur_px(10.0, 0.0) == pytest.approx(0.0)
    assert glow_blur_px(10.0, 0.6) == pytest.approx(6.0)
    assert glow_blur_px(100.0, 1.0) == pytest.approx(48.0)


def test_arc_sweep_deg() -> None:
    assert arc_sweep_deg(0.0) == pytest.approx(0.0)
    assert arc_sweep_deg(0.5) == pytest.approx(180.0)
    assert arc_sweep_deg(1.25) == pytest.approx(360.0)


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
    CircularProgress(id="cp", **clip_kwargs).draw(ctx)
    return ctx.canvas


def test_circular_progress_draws_track_and_arc_in_clip_mode() -> None:
    _, _, progress = playback_times(
        time_t=38.0,
        start=30.0,
        duration=180.0,
        job_duration=210.0,
        time_mode="clip",
    )
    canvas = _draw_ctx(
        t=38.0,
        start=30.0,
        duration=180.0,
        time_mode="clip",
        glow=0.0,
    )
    canvas.drawCircle.assert_called_once()
    canvas.drawArc.assert_called_once()
    args = canvas.drawArc.call_args[0]
    assert args[1] == pytest.approx(-90.0)
    assert args[2] == pytest.approx(arc_sweep_deg(progress))


def test_circular_progress_hides_track_when_disabled() -> None:
    canvas = _draw_ctx(
        t=10.0,
        start=0.0,
        duration=100.0,
        track_visible=False,
        glow=0.0,
    )
    canvas.drawCircle.assert_not_called()
    canvas.drawArc.assert_called_once()


def test_circular_progress_draws_inner_ring_when_dashed() -> None:
    canvas = _draw_ctx(
        t=50.0,
        start=0.0,
        duration=100.0,
        dashed=True,
        glow=0.0,
    )
    assert canvas.drawArc.call_count == 2
    inner_call = canvas.drawArc.call_args_list[0]
    assert inner_call[0][2] == pytest.approx(360.0)
