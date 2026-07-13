"""Tests for std-neon-sunset-gl audio drive and spectrum prep."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from pixfabrica_core.audio.bus import N_SPECTRUM, AudioBusFrame
from pixfabrica_core.clips import JobInfo, PrepareContext
from pixfabrica_core.theme.color import ColorPalette
from pixfabrica_core.theme.typography import FontPalette
from pixfabrica_std.background.neon_sunset_gl import (
    _PREVIEW_STAR_LAYERS_CAP,
    NeonSunsetGL,
    _demo_spectrum_timeline,
    _precompute_beat_decay,
)


def _prepare_ctx(
    tmp_path: Path,
    *,
    audio: dict,
    duration_sec: float = 8.0,
    for_preview: bool = False,
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
    return PrepareContext(
        job=ji,
        temp_dir=td,
        cache_dir=cd,
        audio=audio,
        for_preview=for_preview,
    )


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


def test_demo_spectrum_is_nonzero():
    spec = _demo_spectrum_timeline(10, 30.0)
    assert spec.shape == (10, N_SPECTRUM)
    assert float(spec.max()) > 0.0


def test_spectrum_precompute_without_bus_uses_demo(tmp_path: Path) -> None:
    clip = NeonSunsetGL(id="ns", bus_select="main")
    ctx = _prepare_ctx(tmp_path, audio={}, duration_sec=2 / 30.0)
    asyncio.run(clip.prepare(ctx))
    hist = clip._spectrum_history  # noqa: SLF001
    assert hist.shape == (2, N_SPECTRUM)
    assert float(hist.max()) > 0.0


def test_audio_histories_use_job_wide_range(tmp_path: Path) -> None:
    frames = [
        AudioBusFrame(
            spectrum=[0.0] * N_SPECTRUM,
            bass=0.01,
            mid=0.02,
            high=0.03,
            beat=False,
            amplitude=0.04,
        ),
        AudioBusFrame(
            spectrum=[0.0] * N_SPECTRUM,
            bass=0.8,
            mid=0.6,
            high=0.7,
            beat=True,
            amplitude=0.9,
        ),
    ]
    clip = NeonSunsetGL(id="ns", bus_select="main", sensitivity=2.0)
    ctx = _prepare_ctx(tmp_path, audio={"main": frames}, duration_sec=2 / 30.0)
    asyncio.run(clip.prepare(ctx))

    bass = clip._bass_history  # noqa: SLF001
    mid = clip._mid_history  # noqa: SLF001
    high = clip._high_history  # noqa: SLF001
    amp = clip._amp_history  # noqa: SLF001
    assert bass[1] > bass[0]
    assert mid[1] > mid[0]
    assert high[1] > high[0]
    assert amp[1] > amp[0]


def test_preview_caps_star_layers(tmp_path: Path) -> None:
    clip = NeonSunsetGL(id="ns", star_layers=5)
    ctx = _prepare_ctx(tmp_path, audio={}, for_preview=True)
    asyncio.run(clip.prepare(ctx))
    assert clip._effective_star_layers() == float(_PREVIEW_STAR_LAYERS_CAP)  # noqa: SLF001
