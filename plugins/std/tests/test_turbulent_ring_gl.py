"""Tests for std-turbulent-ring-gl."""

from __future__ import annotations

import asyncio
from pathlib import Path

from pixfabrica_core.clips import JobInfo, PrepareContext
from pixfabrica_core.theme.color import ColorPalette, ColorToken
from pixfabrica_core.theme.typography import FontPalette
from pixfabrica_std.background.turbulent_ring_gl import TurbulentRingGL


def _prepare_ctx(tmp_path: Path) -> PrepareContext:
    ji = JobInfo(
        title="t",
        description="d",
        width=640,
        height=480,
        fps=30.0,
        duration=2.0,
        colors=ColorPalette(),
        typography=FontPalette(),
        locale="en",
    )
    td = tmp_path / "temp"
    cd = tmp_path / "cache"
    td.mkdir(exist_ok=True)
    cd.mkdir(exist_ok=True)
    return PrepareContext(job=ji, temp_dir=td, cache_dir=cd, audio={})


def test_clip_type():
    assert TurbulentRingGL.clip_type == "std-turbulent-ring-gl"


def test_theme_color_defaults():
    clip = TurbulentRingGL(id="ring")
    assert clip.color == ColorToken.PRIMARY
    assert clip.color_secondary == ColorToken.SECONDARY
    assert clip.color_accent == ColorToken.ACCENT


def test_prepare_sets_bounds(tmp_path: Path) -> None:
    clip = TurbulentRingGL(id="ring")
    ctx = _prepare_ctx(tmp_path)
    asyncio.run(clip.prepare(ctx))
    assert clip._bounds_w == 640.0  # noqa: SLF001
    assert clip._bounds_h == 480.0  # noqa: SLF001
