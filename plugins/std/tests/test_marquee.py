"""Tests for std-marquee anchor placement and rotation."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, call

import pytest

from pixfabrica_core.clips import JobInfo, RenderContext, TimeState
from pixfabrica_core.graphics import Rect
from pixfabrica_core.preview_dims import (
    DEFAULT_REFERENCE_HEIGHT,
    preview_dimensions,
    scale_typography_for_job_height,
)
from pixfabrica_core.theme.color import ColorPalette
from pixfabrica_core.theme.typography import FontPalette
from pixfabrica_std.text.marquee import Marquee
from pixfabrica_std.text.skia_font import make_typography_font


def _draw_marquee(**clip_kwargs: Any) -> MagicMock:
    bounds = Rect(0, 0, 800, 600)
    canvas = MagicMock()
    job = JobInfo(
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
    ctx = RenderContext(
        job=job,
        time=TimeState(frame=0, t=0.0),
        bounds=bounds,
        canvas=canvas,
    )
    Marquee(id="test", text="Hello", **clip_kwargs).draw(ctx)
    return canvas


def _loop_period_px(typography: FontPalette, text: str) -> float:
    spec = typography.title_large
    font = make_typography_font(spec)
    font.setLinearMetrics(True)
    return font.measureText(text) + spec.size


def _job_for_surface(
    *,
    surface_w: int,
    surface_h: int,
    design_w: int,
    design_h: int,
    typography: FontPalette,
) -> JobInfo:
    return JobInfo(
        title="t",
        description="d",
        width=surface_w,
        height=surface_h,
        fps=30.0,
        duration=8.0,
        colors=ColorPalette(),
        typography=typography,
        locale="en",
        output_width=design_w,
        output_height=design_h,
    )


def _scroll_phase_fraction(
    marquee: Marquee,
    job: JobInfo,
    typography: FontPalette,
    *,
    text: str,
    t: float,
) -> float:
    period = _loop_period_px(typography, text)
    scroll = (t * job.scale_output_px(marquee.speed)) % period
    return scroll / period


@pytest.mark.parametrize("direction", ["left", "right"])
def test_left_right_translates_anchor_then_rotates(direction: str) -> None:
    canvas = _draw_marquee(
        direction=direction,
        angle=90,
        offset_x=0.25,
        offset_y=0.75,
    )
    assert canvas.translate.call_args_list[0] == call(200.0, 450.0)
    canvas.rotate.assert_called_once_with(90)


@pytest.mark.parametrize("direction", ["up", "down"])
def test_up_down_translates_anchor_then_rotates(direction: str) -> None:
    canvas = _draw_marquee(
        direction=direction,
        angle=-90,
        offset_x=0.25,
        offset_y=0.75,
    )
    assert canvas.translate.call_args_list[0] == call(200.0, 450.0)
    canvas.rotate.assert_called_once_with(-90)


def test_zero_angle_translates_without_rotation() -> None:
    canvas = _draw_marquee(direction="left", angle=0, offset_x=0.25, offset_y=0.75)
    assert canvas.translate.call_args_list[0] == call(200.0, 450.0)
    canvas.rotate.assert_not_called()


def test_offset_x_only_changes_translate_not_tile_positions() -> None:
    canvas_a = _draw_marquee(direction="left", angle=90, offset_x=0.25, offset_y=0.5)
    canvas_b = _draw_marquee(direction="left", angle=90, offset_x=0.75, offset_y=0.5)

    xs_a = [c.args[1] for c in canvas_a.drawString.call_args_list]
    xs_b = [c.args[1] for c in canvas_b.drawString.call_args_list]
    assert xs_a == xs_b
    assert canvas_a.translate.call_args_list[0] != canvas_b.translate.call_args_list[0]


def test_scroll_speed_scales_for_preview_surface() -> None:
    export_job = JobInfo(
        title="t",
        description="d",
        width=1920,
        height=1080,
        fps=30.0,
        duration=8.0,
        colors=ColorPalette(),
        typography=FontPalette(),
        locale="en",
        output_width=1920,
        output_height=1080,
    )
    preview_job = JobInfo(
        title="t",
        description="d",
        width=480,
        height=270,
        fps=30.0,
        duration=8.0,
        colors=ColorPalette(),
        typography=FontPalette(),
        locale="en",
        output_width=1920,
        output_height=1080,
    )
    assert export_job.scale_output_px(100.0) == 100.0
    assert preview_job.scale_output_px(100.0) == pytest.approx(25.0)


def test_preview_matches_export_visual_scroll_rate() -> None:
    job_w, job_h = 1920, 1080
    preview_w, preview_h = preview_dimensions(job_w, job_h)
    text = "My Song Title"
    t = 2.0
    marquee = Marquee(id="test", speed=100.0, text=text, typography_role="title_large")

    base = FontPalette()
    export_typo = scale_typography_for_job_height(
        base, job_height=job_h, reference_height=DEFAULT_REFERENCE_HEIGHT
    )
    preview_typo = export_typo.scale(preview_h / job_h)

    export_job = _job_for_surface(
        surface_w=job_w,
        surface_h=job_h,
        design_w=job_w,
        design_h=job_h,
        typography=export_typo,
    )
    preview_job = _job_for_surface(
        surface_w=preview_w,
        surface_h=preview_h,
        design_w=job_w,
        design_h=job_h,
        typography=preview_typo,
    )

    export_phase = _scroll_phase_fraction(marquee, export_job, export_typo, text=text, t=t)
    preview_phase = _scroll_phase_fraction(marquee, preview_job, preview_typo, text=text, t=t)
    assert export_phase == pytest.approx(preview_phase)
