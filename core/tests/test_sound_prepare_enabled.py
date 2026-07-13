"""SoundClip ``prepare`` skips analysis when disabled."""

from __future__ import annotations

from pathlib import Path

import pytest

from pixfabrica_core.audio.sound import SoundClip
from pixfabrica_core.clips import JobInfo, PrepareContext
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


@pytest.mark.asyncio
async def test_sound_prepare_skips_when_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    analyze_calls: list[str] = []

    def _boom(*_args, **_kwargs) -> Path:
        analyze_calls.append("called")
        raise AssertionError("analyze_to_cache should not run for disabled sounds")

    monkeypatch.setattr("pixfabrica_core.audio.sound.analyze_to_cache", _boom)

    sound = SoundClip(
        id="s1",
        bus="drums",
        source="/fake/audio.mp3",
        enabled=False,
    )
    await sound.prepare(_ctx(tmp_path))

    assert analyze_calls == []
    assert not sound.is_ready
    assert sound.timeline == []


@pytest.mark.asyncio
async def test_sound_prepare_clears_state_when_disabled(tmp_path: Path) -> None:
    sound = SoundClip(
        id="s1",
        bus="drums",
        source="/fake/audio.mp3",
        enabled=True,
    )
    sound._prepare_key = ("key",)  # noqa: SLF001 — simulate prior prepare
    sound._timeline = [object()]  # type: ignore[list-item]

    sound.enabled = False
    await sound.prepare(_ctx(tmp_path))

    assert not sound.is_ready
    assert sound.timeline == []
