"""Tests for std-singularity-gl registration, presets, shader compile, and audio drive."""

from __future__ import annotations

import asyncio
from pathlib import Path

import numpy as np
import pytest

from pixfabrica_core.audio.bus import N_SPECTRUM, AudioBusFrame
from pixfabrica_core.clips import JobInfo, PrepareContext
from pixfabrica_core.theme.color import ColorPalette
from pixfabrica_core.theme.typography import FontPalette
from pixfabrica_std.background.singularity_gl import SingularityGL, _precompute_beat_decay


def test_clip_type_registered() -> None:
    assert SingularityGL.clip_type == "std-singularity-gl"


def test_defaults() -> None:
    clip = SingularityGL(id="n1")
    assert clip.speed == 1.0
    assert clip.zoom == 1.0
    assert clip.luma_alpha == 0.0
    assert clip.opacity == 1.0


def test_shader_compiles() -> None:
    import moderngl

    from pixfabrica_std.background.singularity_gl import _FRAG, _VERT

    ctx = moderngl.create_standalone_context()
    ctx.program(vertex_shader=_VERT, fragment_shader=_FRAG)


def test_presets() -> None:
    presets = {p["id"]: p for p in SingularityGL.clip_presets}
    assert presets["classic"]["values"]["luma_alpha"] == 0.0
    assert presets["portal"]["values"]["luma_alpha"] == 1.0
    assert presets["portal"]["values"]["brightness"] == 1.3


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
    assert decay[1] == pytest.approx(1.0)
    assert decay[3] < decay[1]


def test_bass_history_uses_job_wide_range(tmp_path: Path) -> None:
    frames = [
        AudioBusFrame(
            spectrum=[0.0] * N_SPECTRUM,
            bass=0.01,
            mid=0.0,
            high=0.0,
            beat=False,
            amplitude=0.0,
        ),
        AudioBusFrame(
            spectrum=[0.0] * N_SPECTRUM,
            bass=0.8,
            mid=0.0,
            high=0.0,
            beat=True,
            amplitude=0.0,
        ),
    ]
    clip = SingularityGL(id="sg", bus_select="main", sensitivity=2.0)
    ctx = _prepare_ctx(tmp_path, audio={"main": frames}, duration_sec=2 / 30.0)
    asyncio.run(clip.prepare(ctx))

    bass = clip._bass_history  # noqa: SLF001
    assert bass[1] > bass[0]
    assert bass[1] > 0.5


def test_stem_analyzer_drums_has_visible_bass_swing(tmp_path: Path) -> None:
    from pixfabrica_core.audio.analysis import StemAnalyzer

    audio = Path("web/public/preview-samples/sources/drums.mp3")
    if not audio.exists():
        pytest.skip("preview sample missing")

    tl = StemAnalyzer().analyze(audio, 0.0, 8.0, 30.0)
    clip = SingularityGL(id="sg", bus_select="main", sensitivity=2.5)
    ctx = _prepare_ctx(tmp_path, audio={"main": tl})
    asyncio.run(clip.prepare(ctx))

    bass = clip._bass_history  # noqa: SLF001
    beat = clip._beat_decay_frames  # noqa: SLF001
    assert float(np.percentile(bass, 95)) > 0.35
    assert float(np.std(bass)) > 0.08
    assert float(np.max(beat)) >= 1.0
