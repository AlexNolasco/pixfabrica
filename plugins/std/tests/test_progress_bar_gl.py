import pytest

from pixfabrica_core.graphics import Rect
from pixfabrica_std.progress._progress_common import (
    format_progress_time,
    playback_times,
    track_layout,
)
from pixfabrica_std.progress.progress_bar_gl import ProgressBarGL


def test_width_half_from_left_anchor() -> None:
    layout = track_layout(Rect(0, 0, 1000, 80), offset_x=0.0, width=0.5, anchor_x="left")
    assert layout is not None
    track_x, _, track_w, _ = layout
    assert track_x == pytest.approx(0)
    assert track_w == pytest.approx(500)


def test_offset_x_with_left_anchor() -> None:
    layout = track_layout(Rect(100, 50, 1000, 80), offset_x=0.5, width=0.5, anchor_x="left")
    assert layout is not None
    track_x, track_y, track_w, bounds_h = layout
    assert track_x == pytest.approx(100 + 0.5 * 1000)
    assert track_y == pytest.approx(50)
    assert track_w == pytest.approx(0.5 * 1000)
    assert bounds_h == pytest.approx(80)


def test_center_anchor_grows_from_middle() -> None:
    layout = track_layout(Rect(0, 0, 1000, 80), offset_x=0.5, width=0.5, anchor_x="center")
    assert layout is not None
    track_x, _, track_w, _ = layout
    assert track_w == pytest.approx(500)
    assert track_x == pytest.approx(250)


def test_right_anchor_grows_leftward() -> None:
    layout = track_layout(Rect(0, 0, 1000, 80), offset_x=1.0, width=0.4, anchor_x="right")
    assert layout is not None
    track_x, _, track_w, _ = layout
    assert track_w == pytest.approx(400)
    assert track_x == pytest.approx(600)


def test_track_layout_zero_width_returns_none() -> None:
    assert track_layout(Rect(0, 0, 100, 80), offset_x=0.5, width=0.0) is None


def test_playback_times_job_mode() -> None:
    elapsed, span, progress = playback_times(
        time_t=38.0,
        start=30.0,
        duration=180.0,
        job_duration=210.0,
        time_mode="job",
    )
    assert elapsed == pytest.approx(38.0)
    assert span == pytest.approx(210.0)
    assert progress == pytest.approx(38.0 / 210.0)


def test_playback_times_clip_mode() -> None:
    elapsed, span, progress = playback_times(
        time_t=38.0,
        start=30.0,
        duration=180.0,
        job_duration=210.0,
        time_mode="clip",
    )
    assert elapsed == pytest.approx(8.0)
    assert span == pytest.approx(180.0)
    assert progress == pytest.approx(8.0 / 180.0)


def test_playback_times_clip_mode_clamps_before_start() -> None:
    elapsed, span, progress = playback_times(
        time_t=10.0,
        start=30.0,
        duration=180.0,
        job_duration=210.0,
        time_mode="clip",
    )
    assert elapsed == pytest.approx(0.0)
    assert span == pytest.approx(180.0)
    assert progress == pytest.approx(0.0)


def test_playback_times_clip_mode_clamps_after_end() -> None:
    elapsed, span, progress = playback_times(
        time_t=300.0,
        start=30.0,
        duration=180.0,
        job_duration=210.0,
        time_mode="clip",
    )
    assert elapsed == pytest.approx(180.0)
    assert span == pytest.approx(180.0)
    assert progress == pytest.approx(1.0)


def test_format_progress_time_zero_pads_minutes() -> None:
    assert format_progress_time(8.0) == "00:08"
    assert format_progress_time(189.0) == "03:09"


def test_format_progress_time_hours() -> None:
    assert format_progress_time(3661.0) == "1:01:01"


def test_progress_bar_gl_track_layout_delegates() -> None:
    clip = ProgressBarGL(id="t", width=0.5, offset_x=0.0, anchor_x="left")
    layout = clip._track_layout(Rect(0, 0, 1000, 80))
    assert layout is not None
    assert layout[2] == pytest.approx(500)
