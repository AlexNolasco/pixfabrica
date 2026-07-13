"""Tests for std-eq-led-gl bin grouping, shaping, and bus reactivity."""

from __future__ import annotations

import asyncio
from pathlib import Path

import numpy as np
import pytest

from pixfabrica_core.audio.bus import N_SPECTRUM
from pixfabrica_core.clips import JobInfo, PrepareContext, TimeState
from pixfabrica_core.theme.color import ColorPalette
from pixfabrica_core.theme.typography import FontPalette
from pixfabrica_std.audio.eq_led_gl import (
    _HEADROOM,
    EqLedGL,
    _bin_group_ranges,
    _mean_group,
    _shape_row,
    _strip_layout,
)


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


def test_clip_type():
    assert EqLedGL.clip_type == "std-eq-led-gl"


def test_default_bar_count_is_64():
    assert EqLedGL.model_fields["bar_count"].default == 64


def test_default_glow():
    assert EqLedGL.model_fields["glow"].default == pytest.approx(0.4)


def test_bin_groups_cover_spectrum_without_gaps():
    ranges = _bin_group_ranges(16)
    assert len(ranges) == 16
    assert ranges[0][0] == 0
    assert ranges[-1][1] == N_SPECTRUM - 1
    for i in range(len(ranges) - 1):
        assert ranges[i][1] + 1 == ranges[i + 1][0]


def test_mean_group_averages_range():
    freq = np.linspace(0.0, 1.0, N_SPECTRUM, dtype=np.float32)
    assert _mean_group(freq, 0, 3) == pytest.approx(float(freq[0:4].mean()))


def test_shape_row_zero_when_silent():
    row = np.zeros(16, dtype=np.float32)
    out = _shape_row(row, sensitivity=2.5)
    assert float(out.max()) == 0.0


def test_shape_row_preserves_relative_levels():
    row = np.array([0.2, 0.5, 0.1], dtype=np.float32)
    out = _shape_row(row, sensitivity=1.0)
    assert float(out[1]) > float(out[0]) > float(out[2])
    assert float(out.max()) < _HEADROOM + 0.01


def test_shape_row_avoids_pegging_at_top():
    row = np.ones(16, dtype=np.float32) * 0.85
    out = _shape_row(row, sensitivity=2.5)
    assert float(out.max()) < 0.95
    assert float(out.max()) <= _HEADROOM + 0.01
    assert float((out >= 0.99).mean()) == 0.0


def test_64_bar_count_is_one_to_one():
    ranges = _bin_group_ranges(64)
    assert all(start == end for start, end in ranges)
    assert [start for start, _ in ranges] == list(range(N_SPECTRUM))


def test_strip_layout_full_width():
    left, w = _strip_layout(1920.0, 1.0)
    assert left == 0.0
    assert w == 1920.0


def test_strip_layout_narrow_width_centers():
    left, w = _strip_layout(1000.0, 0.5)
    assert left == 250.0
    assert w == 500.0


def test_grouped_bins_not_mirrored():
    spectrum = [0.1] * N_SPECTRUM
    spectrum[0] = 0.95
    spectrum[-1] = 0.2
    freq = np.asarray(spectrum, dtype="f4")
    ranges = _bin_group_ranges(32)
    left = _mean_group(freq, *ranges[0])
    right = _mean_group(freq, *ranges[-1])
    assert left > right


def test_stem_analyzer_drums_has_dynamic_heights(tmp_path: Path) -> None:
    from pixfabrica_core.audio.analysis import StemAnalyzer

    audio = Path("web/public/preview-samples/sources/drums.mp3")
    if not audio.exists():
        pytest.skip("preview sample missing")

    tl = StemAnalyzer().analyze(audio, 0.0, 8.0, 30.0)
    clip = EqLedGL(id="eq", bus_select="main", sensitivity=2.5, smoothing=0.45)
    ctx = _prepare_ctx(tmp_path, audio={"main": tl})
    asyncio.run(clip.prepare(ctx))

    history = clip._bar_history[:, : clip.bar_count]  # noqa: SLF001
    peaks = history.max(axis=1)
    assert float(np.percentile(peaks, 95)) > 0.2
    assert float(np.std(peaks)) > 0.05
    assert float(peaks.max()) <= 0.95
    assert float((history >= 0.99).mean()) < 0.01

    active = (history > 0.05).mean(axis=0)
    assert float(active.mean()) > 0.3


def _register_plugins() -> None:
    from pixfabrica_core.composition.registry import register_clip_type
    from pixfabrica_core.plugins.discovery import discover_plugins

    for plugin in discover_plugins()[0]:
        for clip_cls in plugin.clip_types:
            register_clip_type(clip_cls)


def _composite_eq_led(glow: float, *, width: int, height: int) -> np.ndarray:
    from pixfabrica_core.audio.bus import AudioBusFrame
    from pixfabrica_core.composition.track import FillLayout, GLTrack
    from pixfabrica_core.fonts.skia_resolver import warmup_typography_palette
    from pixfabrica_core.theme.color import Color, ColorPalette
    from pixfabrica_renderer.compositor import Compositor

    colors = ColorPalette(primary=Color("#00ccff"), background=Color("#101018"))
    ji = JobInfo(
        title="t",
        description="d",
        width=width,
        height=height,
        fps=30.0,
        duration=1.0,
        colors=colors,
        typography=FontPalette(),
        locale="en",
    )
    spec = np.linspace(0.2, 1.0, N_SPECTRUM, dtype=np.float32)
    frame = AudioBusFrame(
        amplitude=0.8,
        bass=0.8,
        mid=0.6,
        high=0.4,
        beat=False,
        spectrum=spec.tolist(),
    )
    audio = {"main": [frame] * 30}
    clip = EqLedGL(
        id="led",
        start=0.0,
        duration=1.0,
        bus_select="main",
        glow=glow,
        bar_count=32,
        max_bar_height=0.25,
    )
    track = GLTrack(id="t", start=0.0, duration=1.0, layout=FillLayout(), clips=[clip])
    ctx = PrepareContext.from_env(ji, audio=audio)
    warmup_typography_palette(ji.typography)
    asyncio.run(track.prepare(ctx))
    compositor = Compositor([track], ji, audio=audio)
    try:
        return np.array(compositor.composite(TimeState(frame=0, t=0.0)).toarray())
    finally:
        compositor.release_worker_resources()


def test_glow_visible_at_full_export_resolution() -> None:
    """Glow must survive GL FBO → Skia compositor at job resolution, not only preview size."""
    _register_plugins()
    off = _composite_eq_led(0.0, width=1920, height=1080)
    on = _composite_eq_led(0.8, width=1920, height=1080)
    diff = np.abs(on.astype(np.int16) - off.astype(np.int16)).sum(axis=2)
    assert int((diff > 5).sum()) > 10_000


def test_glow_extends_below_baseline() -> None:
    """Reference halo is isotropic — bloom appears below the strip baseline, not only above."""
    _register_plugins()
    on = _composite_eq_led(1.0, width=1920, height=1080)
    off = _composite_eq_led(0.0, width=1920, height=1080)
    bright_on = on[:, :, :3].astype(np.int16).sum(axis=2) / 3
    bright_off = off[:, :, :3].astype(np.int16).sum(axis=2) / 3
    bg = float(np.percentile(bright_off, 10))
    # offset_y=0.85 default — sample rows below baseline (lower ~12% of frame).
    y0 = int(1080 * 0.88)
    below = bright_on[y0:, :]
    below_off = bright_off[y0:, :]
    assert int((below > bg + 10).sum()) > 100
    assert float(below.mean()) > float(below_off.mean()) + 2.0


def test_glow_knob_adds_bloom_on_sparse_spectrum() -> None:
    """Additive reference halo is visible on export; sparse bins keep bloom mostly local."""
    _register_plugins()
    from pixfabrica_core.audio.bus import AudioBusFrame
    from pixfabrica_core.composition.track import FillLayout, GLTrack
    from pixfabrica_core.fonts.skia_resolver import warmup_typography_palette
    from pixfabrica_core.theme.color import Color, ColorPalette
    from pixfabrica_renderer.compositor import Compositor

    colors = ColorPalette(primary=Color("#00ccff"), background=Color("#101018"))
    ji = JobInfo(
        title="t",
        description="d",
        width=1920,
        height=1080,
        fps=30.0,
        duration=1.0,
        colors=colors,
        typography=FontPalette(),
        locale="en",
    )
    # Sparse spectrum — only bass columns lit so halos cannot tile the full width.
    spec = [0.95] * (N_SPECTRUM // 6) + [0.05] * (N_SPECTRUM - N_SPECTRUM // 6)
    frame = AudioBusFrame(
        amplitude=0.8,
        bass=0.8,
        mid=0.6,
        high=0.4,
        beat=False,
        spectrum=spec,
    )
    audio = {"main": [frame] * 30}

    async def _render(glow: float) -> np.ndarray:
        clip = EqLedGL(
            id="led",
            start=0.0,
            duration=1.0,
            bus_select="main",
            glow=glow,
            bar_count=32,
            max_bar_height=0.25,
        )
        track = GLTrack(id="t", start=0.0, duration=1.0, layout=FillLayout(), clips=[clip])
        ctx = PrepareContext.from_env(ji, audio=audio)
        warmup_typography_palette(ji.typography)
        await track.prepare(ctx)
        compositor = Compositor([track], ji, audio=audio)
        try:
            return np.array(compositor.composite(TimeState(frame=0, t=0.0)).toarray())
        finally:
            compositor.release_worker_resources()

    off = asyncio.run(_render(0.0))
    full = asyncio.run(_render(1.0))
    diff = np.abs(full.astype(np.int16) - off.astype(np.int16)).sum(axis=2)
    assert int((diff > 30).sum()) > 5_000
