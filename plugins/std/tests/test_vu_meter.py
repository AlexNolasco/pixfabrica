"""Tests for std-vu-meter level mapping and VU ballistics."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from pixfabrica_core.audio.bus import N_SPECTRUM, AudioBusFrame
from pixfabrica_core.clips import JobInfo, PrepareContext, RenderContext, TimeState
from pixfabrica_core.graphics import Rect
from pixfabrica_core.theme.color import ColorPalette
from pixfabrica_core.theme.typography import FontPalette
from pixfabrica_std.audio.vu_meter import (
    _ARC_END_DEG,
    _ARC_MID_DEG,
    _ARC_START_DEG,
    DB_MAX,
    DB_MIN,
    VuMeter,
    _meter_geometry,
    _smooth_amplitude_timeline,
    db_to_skia_deg,
    level_to_db,
    level_to_skia_deg,
)


def _frame(amp: float) -> AudioBusFrame:
    return AudioBusFrame(
        spectrum=[0.0] * N_SPECTRUM,
        bass=0.0,
        mid=0.0,
        high=0.0,
        beat=False,
        amplitude=amp,
    )


def _prepare_ctx(
    tmp_path: Path,
    *,
    fps: float = 30.0,
    frames: int = 30,
    audio: dict | None = None,
) -> PrepareContext:
    ji = JobInfo(
        title="t",
        description="d",
        width=400,
        height=400,
        fps=fps,
        duration=frames / fps,
        colors=ColorPalette(),
        typography=FontPalette(),
        locale="en",
    )
    td = tmp_path / "temp"
    cd = tmp_path / "cache"
    td.mkdir(exist_ok=True)
    cd.mkdir(exist_ok=True)
    return PrepareContext(job=ji, temp_dir=td, cache_dir=cd, audio=audio or {})


def test_level_to_db_endpoints():
    assert level_to_db(0.0) == pytest.approx(DB_MIN)
    assert level_to_db(1.0) == pytest.approx(DB_MAX)


def test_db_to_skia_deg_endpoints():
    assert db_to_skia_deg(DB_MIN) == pytest.approx(_ARC_START_DEG)
    assert db_to_skia_deg(0.0) == pytest.approx(_ARC_MID_DEG)
    assert db_to_skia_deg(DB_MAX) == pytest.approx(_ARC_END_DEG)
    assert level_to_skia_deg(0.5) == pytest.approx(db_to_skia_deg(-8.5))


def test_attack_faster_than_release():
    frames = [_frame(0.0)] * 5 + [_frame(1.0)] * 30 + [_frame(0.0)] * 30
    levels = _smooth_amplitude_timeline(frames, len(frames), fps=30.0, sensitivity=1.0)
    rise_cross = next(i for i in range(5, 35) if levels[i] >= 0.5)
    peak_idx = int(np.argmax(levels[:35]))
    fall_cross = next(i for i in range(peak_idx, len(levels)) if levels[i] <= 0.5)
    assert rise_cross - 5 < fall_cross - peak_idx


def test_offset_positions_pivot():
    cx, cy, _ = _meter_geometry(400.0, 300.0, 1.0, 0.25, 0.75)
    assert cx == pytest.approx(100.0)
    assert cy == pytest.approx(225.0)


def test_prepare_builds_needle_timeline(tmp_path: Path):
    audio = {"main": [_frame(0.2), _frame(0.8), _frame(0.4)]}
    clip = VuMeter(id="vu", bus_select="main", sensitivity=1.0)
    ctx = _prepare_ctx(tmp_path, frames=3, audio=audio)
    asyncio.run(clip.prepare(ctx, Rect(0, 0, 400, 400)))
    assert clip._needle_levels.shape == (3,)  # noqa: SLF001
    assert clip._needle_levels[1] > clip._needle_levels[0]  # noqa: SLF001


def test_draw_invokes_canvas(tmp_path: Path):
    audio = {"main": [_frame(0.5)]}
    clip = VuMeter(id="vu", bus_select="main", glow=0.0)
    ctx = _prepare_ctx(tmp_path, frames=1, audio=audio)
    asyncio.run(clip.prepare(ctx, Rect(0, 0, 320, 320)))

    canvas = MagicMock()
    job = ctx.job
    render = RenderContext(
        job=job,
        time=TimeState(frame=0, t=0.0),
        bounds=Rect(0, 0, 320, 320),
        canvas=canvas,
    )
    clip.draw(render)
    assert canvas.save.called
    assert canvas.drawLine.called


def test_stem_analyzer_drums_reaches_upper_scale(tmp_path: Path) -> None:
    from pixfabrica_core.audio.analysis import StemAnalyzer

    audio = Path("web/public/preview-samples/sources/drums.mp3")
    if not audio.exists():
        pytest.skip("preview sample missing")

    tl = StemAnalyzer().analyze(audio, 0.0, 8.0, 30.0)
    clip = VuMeter(id="vu", bus_select="main", sensitivity=1.0)
    ctx = _prepare_ctx(tmp_path, frames=len(tl), fps=30.0, audio={"main": tl})
    asyncio.run(clip.prepare(ctx, Rect(0, 0, 320, 320)))
    levels = clip._needle_levels  # noqa: SLF001
    assert float(np.percentile(levels, 95)) > 0.45
    assert float(levels.max()) > 0.7
