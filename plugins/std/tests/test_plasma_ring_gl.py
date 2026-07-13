"""Tests for std-plasma-ring-gl audio drive."""

from __future__ import annotations

import asyncio
from pathlib import Path

import numpy as np
import pytest

from pixfabrica_core.audio.bus import N_SPECTRUM, AudioBusFrame
from pixfabrica_core.clips import JobInfo, PrepareContext
from pixfabrica_core.theme.color import ColorPalette
from pixfabrica_core.theme.typography import FontPalette
from pixfabrica_std.audio.plasma_ring_gl import PlasmaRingGL, _normalize_channel


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


def test_normalize_channel_spreads_quiet_and_loud():
    raw = np.array([0.001, 0.01, 0.5], dtype=np.float32)
    out = _normalize_channel(raw)
    assert out[0] == pytest.approx(0.0, abs=1e-4)
    assert out[-1] == pytest.approx(1.0, abs=1e-4)


def test_audio_histories_use_job_wide_range(tmp_path: Path) -> None:
    frames = [
        AudioBusFrame(
            spectrum=[0.0] * N_SPECTRUM,
            bass=0.01,
            mid=0.0,
            high=0.0,
            beat=False,
            amplitude=0.02,
        ),
        AudioBusFrame(
            spectrum=[0.0] * N_SPECTRUM,
            bass=0.8,
            mid=0.0,
            high=0.0,
            beat=True,
            amplitude=0.9,
        ),
    ]
    clip = PlasmaRingGL(id="p", bus_select="main", sensitivity=2.0, smoothing=0.0)
    ctx = _prepare_ctx(tmp_path, audio={"main": frames}, duration_sec=2 / 30.0)
    asyncio.run(clip.prepare(ctx))
    bass = clip._bass_history  # noqa: SLF001
    amp = clip._amp_history  # noqa: SLF001
    assert bass[1] > bass[0]
    assert amp[1] > amp[0]
    assert bass[1] > 0.5
    assert amp[1] > 0.5


def test_stem_analyzer_drums_has_visible_bass_and_amp_swing(tmp_path: Path) -> None:
    from pixfabrica_core.audio.analysis import StemAnalyzer

    audio = Path("web/public/preview-samples/sources/drums.mp3")
    if not audio.exists():
        pytest.skip("preview sample missing")

    tl = StemAnalyzer().analyze(audio, 0.0, 8.0, 30.0)
    clip = PlasmaRingGL(id="p", bus_select="main", sensitivity=2.5, smoothing=0.45)
    ctx = _prepare_ctx(tmp_path, audio={"main": tl})
    asyncio.run(clip.prepare(ctx))

    bass = clip._bass_history  # noqa: SLF001
    amp = clip._amp_history  # noqa: SLF001
    assert float(np.percentile(bass, 95)) > 0.35
    assert float(np.std(bass)) > 0.08
    assert float(np.percentile(amp, 95)) > 0.5
    assert float(np.std(amp)) > 0.1

    radius_swing = float(np.percentile(bass, 95) - np.percentile(bass, 5)) * clip.bass_pulse
    assert radius_swing > 0.08
