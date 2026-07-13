"""Tests for std-marquee-path circular placement and looping."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
import skia

from pixfabrica_core.clips import JobInfo, RenderContext, TimeState
from pixfabrica_core.graphics import Rect
from pixfabrica_core.theme.color import ColorPalette
from pixfabrica_core.theme.typography import FontPalette
from pixfabrica_std.text.path_marquee import PathMarquee
from pixfabrica_std.text.skia_font import make_typography_font


def _job(bounds: Rect) -> JobInfo:
    return JobInfo(
        title="t",
        description="d",
        width=int(bounds.width),
        height=int(bounds.height),
        fps=30.0,
        duration=1.0,
        colors=ColorPalette(),
        typography=FontPalette(),
        locale="en",
    )


def _draw_path_marquee(*, t: float = 0.0, **clip_kwargs: Any) -> MagicMock:
    bounds = Rect(0, 0, 800, 600)
    canvas = MagicMock()
    ctx = RenderContext(
        job=_job(bounds), time=TimeState(frame=0, t=t), bounds=bounds, canvas=canvas
    )
    clip_kwargs.setdefault("text", "Hello")
    PathMarquee(id="test", **clip_kwargs).draw(ctx)
    return canvas


def _snapped_period_px(text: str, *, bounds: Rect, radius_frac: float = 0.35) -> float:
    """Mirror PathMarquee.draw()'s period-snapping so tests stay in sync with it."""
    spec = FontPalette().body_medium
    font = make_typography_font(spec)
    font.setLinearMetrics(True)
    min_period = sum(font.measureText(ch) for ch in text) + spec.size

    radius = radius_frac * min(bounds.width, bounds.height)
    cx, cy = bounds.x + 0.5 * bounds.width, bounds.y + 0.5 * bounds.height
    oval = skia.Rect.MakeXYWH(cx - radius, cy - radius, radius * 2.0, radius * 2.0)
    path = skia.Path()
    path.addArc(oval, 270.0, 359.9)
    length = skia.PathMeasure(path, True).getLength()

    reps = max(1, round(length / min_period))
    return length / reps


def test_empty_text_draws_nothing() -> None:
    canvas = _draw_path_marquee(text="")
    canvas.drawString.assert_not_called()


def test_draws_one_glyph_call_per_character_per_repetition() -> None:
    canvas = _draw_path_marquee(text="AB")
    calls = canvas.drawString.call_args_list
    assert calls
    chars = {c.args[0] for c in calls}
    assert chars <= {"A", "B"}


def test_start_angle_top_places_first_char_at_top_of_circle() -> None:
    canvas = _draw_path_marquee(text="A", start_angle=270, offset_x=0.5, offset_y=0.5, radius=0.35)
    matrix = canvas.concat.call_args_list[0].args[0]
    pt = matrix.mapXY(0, 0)
    cx, cy = 400.0, 300.0
    radius = 0.35 * 600.0
    assert pt.x() == pytest.approx(cx, abs=1.0)
    assert pt.y() == pytest.approx(cy - radius, abs=1.0)


@pytest.mark.parametrize("direction", ["cw", "ccw"])
def test_first_glyph_moves_off_start_point_as_time_advances(direction: str) -> None:
    canvas_start = _draw_path_marquee(text="Hi", direction=direction, t=0.0, speed=100.0)
    canvas_later = _draw_path_marquee(text="Hi", direction=direction, t=0.5, speed=100.0)

    pt_start = canvas_start.concat.call_args_list[0].args[0].mapXY(0, 0)
    pt_later = canvas_later.concat.call_args_list[0].args[0].mapXY(0, 0)
    assert (pt_start.x(), pt_start.y()) != pytest.approx((pt_later.x(), pt_later.y()))


def test_loops_seamlessly_after_one_full_period() -> None:
    text = "Hi"
    speed = 100.0
    bounds = Rect(0, 0, 800, 600)
    period_px = _snapped_period_px(text, bounds=bounds)
    t_wrap = period_px / speed  # exact time for travel to complete one full period

    canvas_a = _draw_path_marquee(text=text, speed=speed, t=0.0)
    canvas_b = _draw_path_marquee(text=text, speed=speed, t=t_wrap)

    pt_a = canvas_a.concat.call_args_list[0].args[0].mapXY(0, 0)
    pt_b = canvas_b.concat.call_args_list[0].args[0].mapXY(0, 0)
    assert pt_a.x() == pytest.approx(pt_b.x(), abs=1e-2)
    assert pt_a.y() == pytest.approx(pt_b.y(), abs=1e-2)


def test_repetitions_do_not_overlap_at_the_seam() -> None:
    """Copies must be spaced >= their own footprint apart all the way around,
    including where the last copy wraps back to meet the first one."""
    text = "Hi"
    bounds = Rect(0, 0, 800, 600)
    canvas = _draw_path_marquee(text=text, radius=0.35, t=0.0)

    spec = FontPalette().body_medium
    font = make_typography_font(spec)
    font.setLinearMetrics(True)
    widths = [font.measureText(ch) for ch in text]
    text_width = sum(widths)

    radius = 0.35 * min(bounds.width, bounds.height)
    cx, cy = bounds.x + 0.5 * bounds.width, bounds.y + 0.5 * bounds.height
    oval = skia.Rect.MakeXYWH(cx - radius, cy - radius, radius * 2.0, radius * 2.0)
    path = skia.Path()
    path.addArc(oval, 270.0, 359.9)
    measure = skia.PathMeasure(path, True)
    length = measure.getLength()

    # Recover each repetition's start distance from the matrices concat()
    # was called with (one per glyph; every len(text)-th one starts a copy).
    matrices = [c.args[0] for c in canvas.concat.call_args_list]
    starts_local = matrices[:: len(text)]

    def dist_of(matrix: skia.Matrix) -> float:
        pt = matrix.mapXY(0, 0)
        for probe in range(0, int(length) + 1, 1):
            p = measure.getPosTan(probe)[0]
            if abs(p.x() - pt.x()) < 0.5 and abs(p.y() - pt.y()) < 0.5:
                return float(probe)
        raise AssertionError("could not locate matrix origin on path")

    starts = sorted(dist_of(m) for m in starts_local)
    gaps = [b - a for a, b in zip(starts, starts[1:], strict=False)]
    gaps.append(length - starts[-1] + starts[0])  # wraparound gap

    assert all(gap >= text_width - 1.0 for gap in gaps)
