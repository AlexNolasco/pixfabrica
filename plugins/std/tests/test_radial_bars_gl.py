"""Tests for std-radial-bars-gl audio drive."""

from __future__ import annotations

import asyncio
from pathlib import Path

import numpy as np
import pytest

from pixfabrica_core.clips import JobInfo, PrepareContext
from pixfabrica_core.theme.color import ColorPalette
from pixfabrica_core.theme.typography import FontPalette
from pixfabrica_std.audio.radial_bars_gl import (
    RadialBarsGL,
    _normalize_columns,
    _shape_ring_drives,
    _soft_saturate,
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


def test_normalize_columns_spreads_quiet_and_loud_rings():
    raw = np.array([[0.0, 0.0], [0.01, 0.02], [1.0, 0.5]], dtype=np.float32)
    out = _normalize_columns(raw, n_bus=3)
    assert out[-1, 0] == pytest.approx(1.0, abs=1e-4)
    assert out[0, 0] == pytest.approx(0.0, abs=1e-4)


def test_soft_saturate_avoids_hard_pin():
    row = np.ones(4, dtype=np.float32)
    out = _soft_saturate(row, gain=3.0)
    assert float(out.max()) < 0.999


def test_shape_ring_drives_keeps_floor():
    row = np.zeros(4, dtype=np.float32)
    out = _shape_ring_drives(row, drive=0.0, sensitivity=2.5)
    assert float(out.min()) == pytest.approx(0.06, abs=1e-5)


def test_stem_analyzer_drums_has_dynamic_arc_sweep(tmp_path: Path) -> None:
    from pixfabrica_core.audio.analysis import StemAnalyzer

    audio = Path("web/public/preview-samples/sources/drums.mp3")
    if not audio.exists():
        pytest.skip("preview sample missing")

    tl = StemAnalyzer().analyze(audio, 0.0, 8.0, 30.0)
    clip = RadialBarsGL(id="rb", bus_select="main", sensitivity=2.5, smoothing=0.45)
    ctx = _prepare_ctx(tmp_path, audio={"main": tl})
    asyncio.run(clip.prepare(ctx))

    history = clip._bar_history[:, : clip.bar_count]  # noqa: SLF001
    outer = history[:, -1]
    inner = history[:, 0]
    assert float(np.percentile(outer, 95)) > 0.35
    assert float(np.std(outer)) > 0.08
    assert float(np.percentile(inner, 95)) > 0.15
    assert float((history >= 0.999).mean()) < 0.001
