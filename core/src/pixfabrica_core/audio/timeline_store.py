"""In-memory reuse of loaded bus timelines (preview sessions)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pixfabrica_core.audio.bus import AudioBusFrame


@dataclass
class TimelineMemoryStore:
    """Hot cache keyed by on-disk NPZ path — avoids re-reading/deserializing per prepare."""

    _by_cache_path: dict[str, list[AudioBusFrame]] = field(default_factory=dict)

    def get(self, cache_file: Path) -> list[AudioBusFrame] | None:
        return self._by_cache_path.get(cache_file.as_posix())

    def put(self, cache_file: Path, timeline: list[AudioBusFrame]) -> None:
        key = cache_file.as_posix()
        if key not in self._by_cache_path:
            self._by_cache_path[key] = timeline
