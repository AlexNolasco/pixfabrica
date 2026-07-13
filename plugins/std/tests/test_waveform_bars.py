"""Tests for std-waveform-bars cluster profile and rendering."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from pixfabrica_core.audio.bus import N_SPECTRUM, AudioBusFrame
from pixfabrica_core.clips import JobInfo, PrepareContext, RenderContext, TimeState
from pixfabrica_core.graphics import Rect
from pixfabrica_core.prepare_diagnostics import PrepareDiagnostics
from pixfabrica_core.theme.color import ColorPalette
from pixfabrica_core.theme.typography import FontPalette
from pixfabrica_std.audio.waveform_bars import (
    WaveformBars,
    _cluster_harmonics,
    _cluster_row,
    _normalize_amplitude_timeline,
    _seed_from_id,
)


def _bounds() -> Rect:
    return Rect(0, 0, 480, 200)


def _frame(amp: float) -> AudioBusFrame:
    return AudioBusFrame(
        spectrum=[0.0] * N_SPECTRUM,
        bass=0.0,
        mid=0.0,
        high=0.0,
        beat=False,
        amplitude=amp,
    )


def _prepare_ctx(tmp_path: Path, *, audio: dict | None = None) -> PrepareContext:
    ji = JobInfo(
        title="t",
        description="d",
        width=480,
        height=200,
        fps=30.0,
        duration=1.0,
        colors=ColorPalette(),
        typography=FontPalette(),
        locale="en",
    )
    td = tmp_path / "temp"
    cd = tmp_path / "cache"
    td.mkdir(exist_ok=True)
    cd.mkdir(exist_ok=True)
    return PrepareContext(
        job=ji,
        temp_dir=td,
        cache_dir=cd,
        audio=audio or {},
        diagnostics=PrepareDiagnostics(),
    )


def test_seed_from_id_is_deterministic() -> None:
    assert _seed_from_id("clip-a") == _seed_from_id("clip-a")
    assert _seed_from_id("clip-a") != _seed_from_id("clip-b")


def test_cluster_row_is_normalized_and_deterministic() -> None:
    x = np.linspace(0.0, 1.0, 24, dtype=np.float64)
    harmonics = _cluster_harmonics(seed=42)
    row = _cluster_row(x, harmonics, t=0.0)
    assert row.shape == (24,)
    assert row.min() >= 0.0
    assert row.max() <= 1.0

    again = _cluster_row(x, _cluster_harmonics(seed=42), t=0.0)
    assert np.array_equal(row, again)

    different_seed = _cluster_row(x, _cluster_harmonics(seed=7), t=0.0)
    assert not np.array_equal(row, different_seed)


def test_cluster_row_ripples_over_time() -> None:
    x = np.linspace(0.0, 1.0, 24, dtype=np.float64)
    harmonics = _cluster_harmonics(seed=42)
    row_t0 = _cluster_row(x, harmonics, t=0.0)
    row_t1 = _cluster_row(x, harmonics, t=5.0)
    assert not np.array_equal(row_t0, row_t1)


def test_normalize_amplitude_timeline_stretches_range() -> None:
    frames = [_frame(0.1), _frame(0.5), _frame(0.9)]
    normalized = _normalize_amplitude_timeline(frames, 3)
    assert normalized.shape == (3,)
    assert normalized[0] < normalized[1] < normalized[2]


def test_prepare_builds_histories(tmp_path: Path) -> None:
    audio = {"main": [_frame(0.2), _frame(0.8), _frame(0.4)]}
    clip = WaveformBars(id="wb-1", bar_count=16)
    ctx = _prepare_ctx(tmp_path, audio=audio)
    asyncio.run(clip.prepare(ctx, _bounds()))

    assert clip._amplitude_history.shape == (30,)  # noqa: SLF001
    assert clip._cluster_history.shape == (30, 16)  # noqa: SLF001


def test_different_clip_ids_get_different_cluster_patterns(tmp_path: Path) -> None:
    ctx = _prepare_ctx(tmp_path)
    a = WaveformBars(id="wb-a", bar_count=20)
    b = WaveformBars(id="wb-b", bar_count=20)
    asyncio.run(a.prepare(ctx, _bounds()))
    asyncio.run(b.prepare(ctx, _bounds()))

    assert not np.array_equal(a._cluster_history, b._cluster_history)  # noqa: SLF001


def test_sustained_amplitude_still_ripples_across_frames(tmp_path: Path) -> None:
    audio = {"main": [_frame(1.0)] * 30}
    clip = WaveformBars(id="wb-sustain", bar_count=20, motion_speed=1.0)
    ctx = _prepare_ctx(tmp_path, audio=audio)
    asyncio.run(clip.prepare(ctx, _bounds()))

    first = clip._cluster_history[0]  # noqa: SLF001
    later = clip._cluster_history[20]  # noqa: SLF001
    assert not np.array_equal(first, later)


def test_zero_motion_speed_keeps_cluster_frozen(tmp_path: Path) -> None:
    clip = WaveformBars(id="wb-frozen", bar_count=20, motion_speed=0.0)
    ctx = _prepare_ctx(tmp_path)
    asyncio.run(clip.prepare(ctx, _bounds()))

    first = clip._cluster_history[0]  # noqa: SLF001
    later = clip._cluster_history[29]  # noqa: SLF001
    assert np.array_equal(first, later)


def test_draw_renders_mirrored_bars(tmp_path: Path) -> None:
    audio = {"main": [_frame(1.0)] * 30}
    clip = WaveformBars(id="wb-draw", bar_count=12, glow=0.0)
    ctx = _prepare_ctx(tmp_path, audio=audio)
    asyncio.run(clip.prepare(ctx, _bounds()))

    canvas = MagicMock()
    render = RenderContext(
        job=ctx.job,
        time=TimeState(frame=29, t=29.0 / 30.0),
        bounds=_bounds(),
        canvas=canvas,
    )
    clip.draw(render)

    assert canvas.save.called
    assert canvas.restore.called
    assert canvas.drawRRect.call_count == clip.bar_count


def test_draw_skips_entirely_when_bar_width_is_zero(tmp_path: Path) -> None:
    audio = {"main": [_frame(1.0)] * 30}
    clip = WaveformBars(id="wb-hidden", bar_count=12, bar_width=0.0)
    ctx = _prepare_ctx(tmp_path, audio=audio)
    asyncio.run(clip.prepare(ctx, _bounds()))

    canvas = MagicMock()
    render = RenderContext(
        job=ctx.job,
        time=TimeState(frame=0, t=0.0),
        bounds=_bounds(),
        canvas=canvas,
    )
    clip.draw(render)

    assert not canvas.save.called
    assert not canvas.drawRRect.called


def test_draw_skips_entirely_when_width_is_zero(tmp_path: Path) -> None:
    audio = {"main": [_frame(1.0)] * 30}
    clip = WaveformBars(id="wb-narrow", bar_count=12, width=0.0)
    ctx = _prepare_ctx(tmp_path, audio=audio)
    asyncio.run(clip.prepare(ctx, _bounds()))

    canvas = MagicMock()
    render = RenderContext(
        job=ctx.job,
        time=TimeState(frame=0, t=0.0),
        bounds=_bounds(),
        canvas=canvas,
    )
    clip.draw(render)

    assert not canvas.save.called
    assert not canvas.drawRRect.called


def test_narrower_width_centers_bars_within_bounds(tmp_path: Path) -> None:
    audio = {"main": [_frame(1.0)] * 30}
    bounds = _bounds()
    clip = WaveformBars(id="wb-half", bar_count=10, width=0.5, bar_width=4.0)
    ctx = _prepare_ctx(tmp_path, audio=audio)
    asyncio.run(clip.prepare(ctx, bounds))

    canvas = MagicMock()
    render = RenderContext(
        job=ctx.job,
        time=TimeState(frame=0, t=0.0),
        bounds=bounds,
        canvas=canvas,
    )
    clip.draw(render)

    lefts = [call.args[0].rect().left() for call in canvas.drawRRect.call_args_list]
    rights = [call.args[0].rect().right() for call in canvas.drawRRect.call_args_list]
    strip_left = min(lefts)
    strip_right = max(rights)
    strip_center = (strip_left + strip_right) / 2.0
    bounds_center = bounds.x + bounds.width / 2.0
    assert strip_center == pytest.approx(bounds_center, abs=1.0)
    assert (strip_right - strip_left) < bounds.width * 0.6


def test_bar_width_scales_with_design_resolution(tmp_path: Path) -> None:
    """bar_width is a design-resolution pixel value; the render surface may be smaller
    (preview) or match 1:1 (full export) — the drawn bar must scale with it so bars
    don't come out relatively thinner at a higher export resolution."""
    bounds = Rect(0, 0, 480, 270)
    ji = JobInfo(
        title="t",
        description="d",
        width=480,
        height=270,
        fps=30.0,
        duration=1.0,
        colors=ColorPalette(),
        typography=FontPalette(),
        locale="en",
        output_width=1920,
        output_height=1080,
    )
    td = tmp_path / "temp"
    cd = tmp_path / "cache"
    td.mkdir(exist_ok=True)
    cd.mkdir(exist_ok=True)
    ctx = PrepareContext(
        job=ji,
        temp_dir=td,
        cache_dir=cd,
        audio={"main": [_frame(1.0)] * 30},
        diagnostics=PrepareDiagnostics(),
    )
    clip = WaveformBars(id="wb-scaled", bar_count=4, bar_width=8.0, glow=0.0)
    asyncio.run(clip.prepare(ctx, bounds))

    canvas = MagicMock()
    render = RenderContext(
        job=ji,
        time=TimeState(frame=0, t=0.0),
        bounds=bounds,
        canvas=canvas,
    )
    clip.draw(render)

    rect = canvas.drawRRect.call_args_list[0].args[0].rect()
    drawn_width = rect.right() - rect.left()
    assert drawn_width == pytest.approx(2.0)  # 8px * (270/1080 surface-to-design ratio)


def test_current_cluster_falls_back_to_zeros_without_history(tmp_path: Path) -> None:
    clip = WaveformBars(id="wb-empty", bar_count=4)
    ctx = _prepare_ctx(tmp_path)
    asyncio.run(clip.prepare(ctx, _bounds()))
    clip._cluster_history = np.zeros((0, 0), dtype=np.float32)  # noqa: SLF001

    render = RenderContext(
        job=ctx.job,
        time=TimeState(frame=0, t=0.0),
        bounds=_bounds(),
        canvas=MagicMock(),
    )
    cluster = clip._current_cluster(render)  # noqa: SLF001
    assert cluster.shape == (4,)
    assert np.array_equal(cluster, np.zeros(4, dtype=np.float32))
