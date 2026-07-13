"""Tests for std-palette-cycle palette resolution and intensity mapping."""

from __future__ import annotations

import asyncio
from pathlib import Path

import numpy as np
import pytest

from pixfabrica_core.audio.bus import N_SPECTRUM, AudioBusFrame
from pixfabrica_core.clips import JobInfo, PrepareContext
from pixfabrica_core.theme.color import Color, ColorPalette
from pixfabrica_core.theme.typography import FontPalette
from pixfabrica_std.effects.palette_cycle_gl import (
    CHROMATIC_TOKENS,
    MAX_PALETTE,
    PaletteCycle,
    PaletteSwatch,
    cycle_phase,
    effective_blend_intensity,
    pad_palette_uniform,
    resolve_palette_colors,
)


def _palette() -> ColorPalette:
    return ColorPalette(
        primary=Color("#ff0000"),
        secondary=Color("#00ff00"),
        tertiary=Color("#0000ff"),
        accent=Color("#ffff00"),
        background=Color("#111111"),
        neutral=Color("#ffffff"),
        neutral_variant=Color("#888888"),
    )


def test_resolve_palette_uses_chromatic_tokens_by_default() -> None:
    colors = resolve_palette_colors([], _palette())
    assert len(colors) == len(CHROMATIC_TOKENS)
    assert colors[0] == _palette().primary.rgba[:3]
    assert colors[1] == _palette().secondary.rgba[:3]
    assert colors[2] == _palette().tertiary.rgba[:3]
    assert colors[3] == _palette().accent.rgba[:3]


def test_resolve_palette_custom_replaces_theme() -> None:
    c0 = Color("#112233")
    c1 = Color("#445566")
    custom = [PaletteSwatch(color=c0), PaletteSwatch(color=c1)]
    colors = resolve_palette_colors(custom, _palette())
    assert colors == [c0.rgba[:3], c1.rgba[:3]]


def test_effective_blend_without_bus_uses_intensity_only() -> None:
    assert (
        effective_blend_intensity(
            intensity=0.6,
            sensitivity=0.5,
            amplitude=1.0,
            bus_connected=False,
        )
        == 0.6
    )


def test_effective_blend_with_bus_scales_by_amplitude() -> None:
    assert (
        effective_blend_intensity(
            intensity=1.0,
            sensitivity=1.0,
            amplitude=0.0,
            bus_connected=True,
        )
        == 0.5
    )
    assert (
        effective_blend_intensity(
            intensity=1.0,
            sensitivity=1.0,
            amplitude=1.0,
            bus_connected=True,
        )
        == 1.0
    )
    assert (
        effective_blend_intensity(
            intensity=0.8,
            sensitivity=1.0,
            amplitude=1.0,
            bus_connected=True,
        )
        == 0.8
    )


def test_pad_palette_uniform_fills_to_max() -> None:
    short = [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]
    padded = pad_palette_uniform(short)
    assert len(padded) == MAX_PALETTE
    assert padded[:2] == short
    assert padded[2:] == [(0.0, 0.0, 0.0)] * (MAX_PALETTE - 2)


def test_cycle_phase_wraps_and_includes_offset() -> None:
    assert cycle_phase(offset=0.25, time_s=0.0, speed=1.0) == 0.25
    assert cycle_phase(offset=0.0, time_s=2.0, speed=0.5) == 0.0
    assert cycle_phase(offset=0.1, time_s=1.8, speed=1.0) == pytest.approx(0.9)


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


def test_amp_history_uses_job_wide_range(tmp_path: Path) -> None:
    frames = [
        AudioBusFrame(
            spectrum=[0.0] * N_SPECTRUM,
            bass=0.0,
            mid=0.0,
            high=0.0,
            beat=False,
            amplitude=0.02,
        ),
        AudioBusFrame(
            spectrum=[0.0] * N_SPECTRUM,
            bass=0.0,
            mid=0.0,
            high=0.0,
            beat=False,
            amplitude=0.9,
        ),
    ]
    clip = PaletteCycle(id="pc", bus_select="main")
    ctx = _prepare_ctx(tmp_path, audio={"main": frames}, duration_sec=2 / 30.0)
    asyncio.run(clip.prepare(ctx))

    amp = clip._amp_history  # noqa: SLF001
    assert amp[1] > amp[0]
    assert amp[1] > 0.5


def test_stem_analyzer_drums_has_visible_amp_swing(tmp_path: Path) -> None:
    from pixfabrica_core.audio.analysis import StemAnalyzer

    audio = Path("web/public/preview-samples/sources/drums.mp3")
    if not audio.exists():
        pytest.skip("preview sample missing")

    tl = StemAnalyzer().analyze(audio, 0.0, 8.0, 30.0)
    clip = PaletteCycle(id="pc", bus_select="main")
    ctx = _prepare_ctx(tmp_path, audio={"main": tl})
    asyncio.run(clip.prepare(ctx))

    amp = clip._amp_history  # noqa: SLF001
    assert float(np.percentile(amp, 95)) > 0.5
    assert float(np.std(amp)) > 0.1
