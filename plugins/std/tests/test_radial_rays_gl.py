"""Tests for std-radial-rays-gl StemAnalyzer reactivity."""

from __future__ import annotations

import asyncio
from pathlib import Path

import numpy as np
import pytest

from pixfabrica_core.clips import JobInfo, PrepareContext
from pixfabrica_core.theme.color import ColorPalette
from pixfabrica_core.theme.typography import FontPalette
from pixfabrica_std.audio.radial_rays_gl import RadialRaysGL, _clip_progress, _shape_ray_row


def _prepare_ctx(tmp_path: Path, *, audio: dict) -> PrepareContext:
    ji = JobInfo(
        title="t",
        description="d",
        width=640,
        height=480,
        fps=30.0,
        duration=8.0,
        colors=ColorPalette(),
        typography=FontPalette(),
        locale="en",
    )
    td = tmp_path / "temp"
    cd = tmp_path / "cache"
    td.mkdir(exist_ok=True)
    cd.mkdir(exist_ok=True)
    return PrepareContext(job=ji, temp_dir=td, cache_dir=cd, audio=audio)


def test_shape_ray_row_uses_frame_peak_not_per_ray_column():
    row = np.array([0.05, 0.5, 0.25, 0.1], dtype=np.float32)
    out = _shape_ray_row(row, drive=1.0, sensitivity=1.0)
    assert float(out.max()) <= 1.0
    assert out[1] == max(out)


def test_clip_progress_uses_clip_span():
    assert _clip_progress(time_t=2.0, start=1.0, duration=4.0, job_duration=10.0) == 0.25
    assert _clip_progress(time_t=6.0, start=2.0, duration=4.0, job_duration=10.0) == 1.0
    assert _clip_progress(time_t=0.5, start=2.0, duration=4.0, job_duration=10.0) == 0.0


def test_bass_drive_precomputed_on_drums(tmp_path: Path) -> None:
    from pixfabrica_core.audio.analysis import StemAnalyzer

    audio = Path("web/public/preview-samples/sources/drums.mp3")
    if not audio.exists():
        pytest.skip("preview sample missing")

    tl = StemAnalyzer().analyze(audio, 0.0, 8.0, 30.0)
    clip = RadialRaysGL(id="rr", bus_select="main", scale_pulse=0.12)
    ctx = _prepare_ctx(tmp_path, audio={"main": tl})
    asyncio.run(clip.prepare(ctx))

    bass = clip._bass_drive  # noqa: SLF001
    assert bass.shape[0] == ctx.job.total_frames
    assert float(np.percentile(bass, 95)) > 0.2
    assert float(np.std(bass)) > 0.05


def test_stem_analyzer_drums_has_dynamic_ray_heights(tmp_path: Path) -> None:
    from pixfabrica_core.audio.analysis import StemAnalyzer

    audio = Path("web/public/preview-samples/sources/drums.mp3")
    if not audio.exists():
        pytest.skip("preview sample missing")

    tl = StemAnalyzer().analyze(audio, 0.0, 8.0, 30.0)
    clip = RadialRaysGL(id="rr", bus_select="main", sensitivity=2.5, smoothing=0.4)
    ctx = _prepare_ctx(tmp_path, audio={"main": tl})
    asyncio.run(clip.prepare(ctx))

    history = clip._bar_history[:, : clip.ray_count]  # noqa: SLF001
    peaks = history.max(axis=1)
    assert float(np.percentile(peaks, 50)) > 0.15
    assert float(np.percentile(peaks, 95)) > 0.5
    assert float(np.std(peaks)) > 0.1
    assert float(peaks.max()) <= 1.0
