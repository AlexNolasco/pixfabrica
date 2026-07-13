from __future__ import annotations

import asyncio
import hashlib
import logging
from pathlib import Path
from typing import ClassVar

from pydantic import Field, PrivateAttr

from pixfabrica_core.audio.analysis import AnalysisCancelledError, _resolve_source
from pixfabrica_core.audio.bus import AudioBusFrame
from pixfabrica_core.audio.cache import (
    analyze_to_cache,
    load_cached_timeline,
    timeline_cache_path_for_file,
)
from pixfabrica_core.clips.base import Clip, ClipCategory, PrepareContext
from pixfabrica_core.prepare_diagnostics import record_prepare_asset_failure

log = logging.getLogger(__name__)


class SoundClip(Clip):
    """Analyze a single audio file (mix or one-shot) onto a flat audio bus."""

    sound_type: ClassVar[str] = "std-sound"
    clip_category: ClassVar[ClipCategory] = ClipCategory.AUDIO

    source: str = Field(description="Local path or http(s) URL to the audio file")
    bus: str = Field(description="Named audio bus, e.g. 'main'")
    volume: float = Field(default=1.0, ge=0.0, le=2.0, description="Playback volume multiplier")
    seek: float = Field(default=0.0, ge=0.0, description="Seconds into source to start reading")
    beat_tightness: float = Field(
        default=200.0,
        ge=1.0,
        le=1000.0,
        description="Rhythm peak strictness; higher = fewer beat/onset flags",
    )

    _local_path: Path | None = PrivateAttr(default=None)
    _timeline: list[AudioBusFrame] = PrivateAttr(default_factory=list)
    _prepare_key: tuple | None = PrivateAttr(default=None)

    @property
    def is_ready(self) -> bool:
        return self._prepare_key is not None

    @property
    def local_path(self) -> Path | None:
        return self._local_path

    @property
    def mix_key(self) -> str:
        data = (
            f"{self.source}|{self.start}|{self.seek}|{self.duration}|{self.volume}|{self.enabled}"
        )
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    @property
    def timeline(self) -> list[AudioBusFrame]:
        return self._timeline

    async def prepare(self, ctx: PrepareContext, _bounds=None) -> None:
        if not self.enabled:
            self._prepare_key = None
            self._timeline = []
            self._local_path = None
            return

        key = (self.source, self.seek, self.duration, self.beat_tightness)
        if key == self._prepare_key:
            return

        try:
            local_path = await _resolve_source(self.source, ctx)
        except Exception as exc:
            record_prepare_asset_failure(
                ctx,
                kind="sound",
                ref_id=self.id,
                clip_type=self.sound_type,
                field="source",
                source=self.source,
                exc=exc,
            )
            log.warning("SoundClip %s: could not resolve source %r — %s", self.id, self.source, exc)
            return
        self._local_path = local_path

        cache_file = timeline_cache_path_for_file(
            ctx.cache_dir,
            local_path,
            self.seek,
            self.duration,
            ctx.job.fps,
            self.beat_tightness,
        )
        loop = asyncio.get_running_loop()

        store = ctx.timeline_store
        if store is not None:
            cached = store.get(cache_file)
            if cached is not None:
                self._timeline = cached
                self._prepare_key = key
                return

        if cache_file.exists():
            loaded = await loop.run_in_executor(None, load_cached_timeline, cache_file)
            if loaded:
                self._timeline = loaded
                self._prepare_key = key
                if store is not None:
                    store.put(cache_file, self._timeline)
                return

        log.info("bus '%s': analyzer=stem preview=%s", self.bus, ctx.for_preview)
        try:
            await loop.run_in_executor(
                None,
                lambda: analyze_to_cache(
                    cache_dir=ctx.cache_dir,
                    local_path=local_path,
                    seek=self.seek,
                    duration=self.duration,
                    fps=ctx.job.fps,
                    beat_tightness=self.beat_tightness,
                    cancel=ctx.cancel,
                ),
            )
        except AnalysisCancelledError:
            return

        self._timeline = await loop.run_in_executor(None, load_cached_timeline, cache_file)
        self._prepare_key = key
        if store is not None:
            store.put(cache_file, self._timeline)
