"""Tests for std-neon-tunnel-gl audio drive."""

from __future__ import annotations

import asyncio
from pathlib import Path

import numpy as np
import pytest

from pixfabrica_core.audio.bus import N_SPECTRUM, AudioBusFrame
from pixfabrica_core.clips import JobInfo, PrepareContext
from pixfabrica_core.theme.color import ColorPalette
from pixfabrica_core.theme.typography import FontPalette
from pixfabrica_std.background.neon_tunnel_gl import NeonTunnelGL, _precompute_beat_decay


def _prepare_ctx(
    tmp_path: Path,
    *,
    audio: dict,
    duration_sec: float = 8.0,
) -> PrepareContext:
    ji = JobInfo(
        title="t",
        description="d",
        width=640,
        height=480,
        fps=30.0,
        duration=duration_sec,
        colors=ColorPalette(),
        typography=FontPalette(),
        locale="en",
    )
    td = tmp_path / "temp"
    cd = tmp_path / "cache"
    td.mkdir(exist_ok=True)
    cd.mkdir(exist_ok=True)
    return PrepareContext(job=ji, temp_dir=td, cache_dir=cd, audio=audio)


def test_beat_decay_spans_job_and_peaks_on_beat():
    frames = [
        AudioBusFrame(
            spectrum=[0.0] * N_SPECTRUM,
            bass=0.0,
            mid=0.0,
            high=0.0,
            beat=False,
            amplitude=0.0,
        ),
        AudioBusFrame(
            spectrum=[0.0] * N_SPECTRUM,
            bass=0.0,
            mid=0.0,
            high=0.0,
            beat=True,
            amplitude=0.0,
        ),
    ]
    decay = _precompute_beat_decay(frames, total=4)
    assert decay.shape[0] == 4
    assert decay[1] == pytest.approx(1.5)
    assert decay[3] < decay[1]


def test_audio_histories_use_job_wide_range(tmp_path: Path) -> None:
    frames = [
        AudioBusFrame(
            spectrum=[0.0] * N_SPECTRUM,
            bass=0.01,
            mid=0.0,
            high=0.02,
            beat=False,
            amplitude=0.0,
        ),
        AudioBusFrame(
            spectrum=[0.0] * N_SPECTRUM,
            bass=0.8,
            mid=0.0,
            high=0.7,
            beat=True,
            amplitude=0.0,
        ),
    ]
    clip = NeonTunnelGL(id="nt", bus_select="main", sensitivity=2.0)
    ctx = _prepare_ctx(tmp_path, audio={"main": frames}, duration_sec=2 / 30.0)
    asyncio.run(clip.prepare(ctx))

    bass = clip._bass_history  # noqa: SLF001
    high = clip._high_history  # noqa: SLF001
    assert bass[1] > bass[0]
    assert high[1] > high[0]
    assert bass[1] > 0.5
    assert high[1] > 0.5


def test_stem_analyzer_drums_has_visible_bass_high_swing(tmp_path: Path) -> None:
    from pixfabrica_core.audio.analysis import StemAnalyzer

    audio = Path("web/public/preview-samples/sources/drums.mp3")
    if not audio.exists():
        pytest.skip("preview sample missing")

    tl = StemAnalyzer().analyze(audio, 0.0, 8.0, 30.0)
    clip = NeonTunnelGL(id="nt", bus_select="main", sensitivity=2.5)
    ctx = _prepare_ctx(tmp_path, audio={"main": tl})
    asyncio.run(clip.prepare(ctx))

    bass = clip._bass_history  # noqa: SLF001
    high = clip._high_history  # noqa: SLF001
    beat = clip._beat_decay_frames  # noqa: SLF001

    assert float(np.percentile(bass, 95)) > 0.35
    assert float(np.std(bass)) > 0.08
    assert float(np.percentile(high, 95)) > 0.25
    assert float(np.std(high)) > 0.05
    assert float(np.max(beat)) >= 1.5
