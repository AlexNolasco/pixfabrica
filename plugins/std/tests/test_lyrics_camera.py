"""Tests for std-lyrics-camera sheet bake and camera follow."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from pixfabrica_core.clips import JobInfo, PrepareContext, RenderContext, TimeState
from pixfabrica_core.graphics import Rect
from pixfabrica_core.theme.color import ColorPalette
from pixfabrica_core.theme.typography import FontPalette
from pixfabrica_std.text.lyrics_camera import LyricsCamera


def _job(*, fps: float = 30.0, duration: float = 4.0) -> JobInfo:
    return JobInfo(
        title="t",
        description="d",
        width=800,
        height=600,
        fps=fps,
        duration=duration,
        colors=ColorPalette(),
        typography=FontPalette(),
        locale="en",
    )


def _ctx(tmp_path: Path, job: JobInfo | None = None) -> PrepareContext:
    ji = job or _job()
    return PrepareContext(job=ji, temp_dir=tmp_path / "tmp", cache_dir=tmp_path / "cache")


def _lrc(tmp_path: Path) -> Path:
    path = tmp_path / "sample.lrc"
    path.write_text(
        "\n".join(
            [
                "[00:00.00]First line of the song",
                "[00:01.00]Second line arrives",
                "[00:02.50]Third line holds longer",
                "[00:03.50]Fourth and final",
            ]
        ),
        encoding="utf-8",
    )
    return path


def test_prepare_bakes_sheet_and_camera_table(tmp_path: Path) -> None:
    job = _job(fps=10.0, duration=4.0)
    clip = LyricsCamera(id="cam", source=str(_lrc(tmp_path)), follow_speed=30.0, context_lines=3)
    bounds = Rect(0, 0, 800, 600)
    clip._prepare_sync(_ctx(tmp_path, job), bounds)

    assert clip._sheet is not None
    assert clip._sheet.width() > 0
    assert clip._sheet.height() > 0
    assert clip._cam_y.shape == (job.total_frames,)
    assert clip._cam_x.shape == (job.total_frames,)
    assert clip._cam_scale.shape == (job.total_frames,)
    assert float(clip._cam_scale[0]) > 0.0


def test_camera_holds_last_segment_between_gaps(tmp_path: Path) -> None:
    srt = tmp_path / "gapped.srt"
    srt.write_text(
        "\n".join(
            [
                "1",
                "00:00:00,000 --> 00:00:01,000",
                "First line",
                "",
                "2",
                "00:00:02,000 --> 00:00:03,000",
                "Second after a gap",
                "",
            ]
        ),
        encoding="utf-8",
    )
    job = _job(fps=10.0, duration=3.5)
    clip = LyricsCamera(id="cam", source=str(srt), follow_speed=30.0)
    clip._prepare_sync(_ctx(tmp_path, job), Rect(0, 0, 800, 600))

    y_first = float(clip._cam_y[5])  # t=0.5 → first
    y_gap = float(clip._cam_y[15])  # t=1.5 → hold first through gap
    y_second = float(clip._cam_y[25])  # t=2.5 → second
    assert y_gap == pytest.approx(y_first, abs=2.0)
    assert y_second > y_first


def test_camera_moves_down_as_lyrics_advance(tmp_path: Path) -> None:
    job = _job(fps=10.0, duration=4.0)
    clip = LyricsCamera(id="cam", source=str(_lrc(tmp_path)), follow_speed=30.0)
    clip._prepare_sync(_ctx(tmp_path, job), Rect(0, 0, 800, 600))

    y0 = float(clip._cam_y[2])  # first
    y1 = float(clip._cam_y[12])  # second
    y2 = float(clip._cam_y[30])  # third
    assert y1 > y0
    assert y2 > y1


def test_draw_applies_tilt_and_draws_sheet(tmp_path: Path) -> None:
    job = _job(fps=10.0, duration=2.0)
    clip = LyricsCamera(
        id="cam",
        source=str(_lrc(tmp_path)),
        angle=7.0,
        pitch=0.0,
        opacity=0.8,
        dof_strength=0.0,
    )
    bounds = Rect(0, 0, 800, 600)
    clip._prepare_sync(_ctx(tmp_path, job), bounds)

    canvas = MagicMock()
    ctx = RenderContext(
        job=job,
        time=TimeState(frame=5, t=0.5),
        bounds=bounds,
        canvas=canvas,
    )
    clip.draw(ctx)

    canvas.save.assert_called()
    canvas.clipRect.assert_called()
    canvas.rotate.assert_called_with(7.0)
    canvas.concat.assert_not_called()
    canvas.drawImage.assert_called()
    assert canvas.drawImage.call_args.kwargs.get("paint") is not None
    canvas.restore.assert_called()


def test_pitch_applies_perspective_matrix(tmp_path: Path) -> None:
    job = _job(fps=10.0, duration=2.0)
    clip = LyricsCamera(
        id="cam",
        source=str(_lrc(tmp_path)),
        pitch=15.0,
        angle=0.0,
        dof_strength=0.0,
    )
    bounds = Rect(0, 0, 400, 300)
    clip._prepare_sync(_ctx(tmp_path, job), bounds)

    canvas = MagicMock()
    ctx = RenderContext(
        job=job,
        time=TimeState(frame=5, t=0.5),
        bounds=bounds,
        canvas=canvas,
    )
    clip.draw(ctx)

    canvas.concat.assert_called()
    matrix = canvas.concat.call_args.args[0]
    assert matrix.hasPerspective()
    # Positive pitch → look down → negative perspY (top shrinks).
    assert clip._pitch_persp_y(bounds.height) < 0.0
    assert matrix.getPerspY() == pytest.approx(clip._pitch_persp_y(bounds.height))


def test_draw_with_dof_composites_blur_and_sharp(tmp_path: Path) -> None:
    job = _job(fps=10.0, duration=2.0)
    clip = LyricsCamera(id="cam", source=str(_lrc(tmp_path)), dof_strength=0.7, angle=5.0)
    bounds = Rect(0, 0, 320, 180)
    clip._prepare_sync(_ctx(tmp_path, job), bounds)

    canvas = MagicMock()
    ctx = RenderContext(
        job=job,
        time=TimeState(frame=5, t=0.5),
        bounds=bounds,
        canvas=canvas,
    )
    clip.draw(ctx)

    # Blurred base + sharp layer (saveLayer) should hit the destination canvas.
    assert canvas.drawImage.call_count >= 1
    canvas.saveLayer.assert_called()
    assert float(clip._dof_sigma(bounds.width, bounds.height)) > 0.0


def test_empty_source_skips_prepare(tmp_path: Path) -> None:
    clip = LyricsCamera(id="cam", source="")
    clip._prepare_sync(_ctx(tmp_path), Rect(0, 0, 800, 600))
    assert clip._sheet is None
    assert clip._cam_y.size == 0
