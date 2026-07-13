"""In-memory bus timeline reuse during preview prepare."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from pixfabrica_core.audio.analysis import save_timeline_cache
from pixfabrica_core.audio.bus import AudioBusFrame
from pixfabrica_core.audio.cache import timeline_cache_path_for_file
from pixfabrica_core.audio.sound import SoundClip
from pixfabrica_core.audio.timeline_store import TimelineMemoryStore
from pixfabrica_core.clips import JobInfo, PrepareContext
from pixfabrica_core.theme.color import ColorPalette
from pixfabrica_core.theme.typography import FontPalette


def _ctx(tmp_path: Path, store: TimelineMemoryStore | None = None) -> PrepareContext:
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
    return PrepareContext(
        job=ji,
        temp_dir=td,
        cache_dir=cd,
        for_preview=True,
        timeline_store=store,
    )


@pytest.mark.asyncio
async def test_sound_prepare_reuses_timeline_memory_store(tmp_path: Path) -> None:
    audio = tmp_path / "tone.wav"
    audio.write_bytes(b"fake-wav")
    timeline = [AudioBusFrame.zero() for _ in range(3)]
    cache_file = timeline_cache_path_for_file(
        tmp_path / "cache",
        audio,
        0.0,
        None,
        30.0,
        200.0,
    )
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    save_timeline_cache(cache_file, timeline)
    store = TimelineMemoryStore()
    ctx = _ctx(tmp_path, store=store)

    with (
        patch(
            "pixfabrica_core.audio.sound._resolve_source",
            new=AsyncMock(return_value=audio),
        ),
        patch(
            "pixfabrica_core.audio.sound.load_cached_timeline",
            return_value=timeline,
        ) as load_mock,
    ):
        sound_a = SoundClip(id="s1", bus="main", source=str(audio))
        await sound_a.prepare(ctx)
        assert load_mock.call_count == 1

        load_mock.reset_mock()
        sound_b = SoundClip(id="s2", bus="main", source=str(audio))
        await sound_b.prepare(ctx)
        load_mock.assert_not_called()
        assert sound_b.timeline is sound_a.timeline
