"""Tests for std-star-pulse-gl registration, presets, shader compile, and audio drive."""

from __future__ import annotations

import pytest

from pixfabrica_core.audio.bus import AudioBusFrame
from pixfabrica_core.clips import JobInfo, PrepareContext
from pixfabrica_core.theme.color import ColorPalette
from pixfabrica_core.theme.typography import FontPalette
from pixfabrica_std.audio.star_pulse_gl import (
    StarPulseGL,
    _amp_size_multiplier,
    _precompute_audio_drive,
)


def test_clip_type_registered() -> None:
    assert StarPulseGL.clip_type == "std-star-pulse-gl"


def test_defaults() -> None:
    clip = StarPulseGL(id="n1")
    assert clip.width == 0.4
    assert clip.points == 6
    assert clip.speed == 1.0
    assert clip.sensitivity == 2.5
    assert clip.luma_alpha == 0.0


def test_shader_compiles() -> None:
    import moderngl

    from pixfabrica_std.audio.star_pulse_gl import _FRAG, _VERT

    ctx = moderngl.create_standalone_context()
    ctx.program(vertex_shader=_VERT, fragment_shader=_FRAG)


def test_presets() -> None:
    presets = {p["id"]: p for p in StarPulseGL.clip_presets}
    assert presets["overlay"]["values"]["luma_alpha"] == 1.0
    assert presets["octa_burst"]["values"]["points"] == 8
    assert presets["octa_burst"]["values"]["width"] == 0.3


def test_amp_size_multiplier_idle_and_hot() -> None:
    assert _amp_size_multiplier(0.0) == pytest.approx(1.0)
    assert _amp_size_multiplier(1.0) > 1.0


def test_precompute_audio_drive_empty_without_bus() -> None:
    bass, amp = _precompute_audio_drive(total_frames=10, bus_frames=None, sensitivity=2.5)
    assert bass.shape == (10,)
    assert amp.shape == (10,)
    assert bass.max() == 0.0
    assert amp.max() == 0.0


def test_precompute_audio_drive_responds_to_bass_and_amp() -> None:
    frames = [AudioBusFrame.zero() for _ in range(30)]
    frames[10] = AudioBusFrame.zero().model_copy(
        update={"bass": 1.0, "amplitude": 1.0, "onset": True}
    )
    bass, amp = _precompute_audio_drive(
        total_frames=30,
        bus_frames=frames,
        sensitivity=2.5,
    )
    assert bass[15] > 0.0
    assert amp[15] > 0.0


def test_prepare_builds_histories(tmp_path) -> None:
    import asyncio
    from pathlib import Path

    frames = [
        AudioBusFrame.zero().model_copy(update={"bass": 0.2, "amplitude": 0.3}),
        AudioBusFrame.zero().model_copy(update={"bass": 0.8, "amplitude": 0.7}),
    ]
    ji = JobInfo(
        title="t",
        description="d",
        width=640,
        height=360,
        fps=30.0,
        duration=2 / 30.0,
        colors=ColorPalette(),
        typography=FontPalette(),
        locale="en",
    )
    td = Path(tmp_path) / "temp"
    cd = Path(tmp_path) / "cache"
    td.mkdir()
    cd.mkdir()
    ctx = PrepareContext(job=ji, temp_dir=td, cache_dir=cd, audio={"main": frames})

    clip = StarPulseGL(id="sp", bus_select="main", sensitivity=2.0)
    asyncio.run(clip.prepare(ctx))
    assert clip._bass_history.shape[0] == 2  # noqa: SLF001
    assert clip._amp_history[1] > clip._amp_history[0]  # noqa: SLF001
