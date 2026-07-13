"""Track ``prepare`` respects ``enabled`` on the track and each clip."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import pytest

from pixfabrica_core.clips import ClipCategory, ClipSkia, JobInfo, PrepareContext, RenderContext
from pixfabrica_core.composition.track import SkiaTrack
from pixfabrica_core.graphics import Rect
from pixfabrica_core.theme.color import ColorPalette
from pixfabrica_core.theme.typography import FontPalette


def _ctx(tmp_path: Path) -> PrepareContext:
    ji = JobInfo(
        title="t",
        description="d",
        width=640,
        height=480,
        fps=30.0,
        duration=1.0,
        colors=ColorPalette(),
        typography=FontPalette(),
        locale="en",
    )
    td = tmp_path / "temp"
    cd = tmp_path / "cache"
    td.mkdir()
    cd.mkdir()
    return PrepareContext(job=ji, temp_dir=td, cache_dir=cd)


prep_log: list[str] = []


class _SkiaStub(ClipSkia):
    clip_type: ClassVar[str] = "core-test-skia-stub"
    clip_category: ClassVar[ClipCategory] = ClipCategory.IMAGE

    async def prepare(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        prep_log.append(self.id)

    def draw(self, ctx: RenderContext) -> None:
        pass


@pytest.mark.asyncio
async def test_prepare_skips_disabled_track(tmp_path: Path) -> None:
    prep_log.clear()
    el = _SkiaStub(id="e1", start=0.0, duration=1.0)
    track = SkiaTrack(id="t1", start=0.0, duration=1.0, enabled=False, clips=[el])
    await track.prepare(_ctx(tmp_path))
    assert prep_log == []


@pytest.mark.asyncio
async def test_prepare_skips_disabled_clip(tmp_path: Path) -> None:
    prep_log.clear()
    el_on = _SkiaStub(id="e1", start=0.0, duration=1.0, enabled=True)
    el_off = _SkiaStub(id="e2", start=0.0, duration=1.0, enabled=False)
    track = SkiaTrack(id="t1", start=0.0, duration=1.0, clips=[el_on, el_off])
    await track.prepare(_ctx(tmp_path))
    assert prep_log == ["e1"]
