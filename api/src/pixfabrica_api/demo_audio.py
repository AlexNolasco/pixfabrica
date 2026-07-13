"""Pre-baked demo audio bus for isolated clip preview."""

from __future__ import annotations

import asyncio
import logging
from functools import lru_cache
from pathlib import Path

from pixfabrica_core.audio import AnalyzerKind
from pixfabrica_core.audio.analysis import get_analyzer
from pixfabrica_core.audio.bus import AudioBusFrame, AudioTimeline

log = logging.getLogger("pixfabrica.api.demo_audio")

_SNIPPET_PATH = Path(__file__).resolve().parents[2] / "media" / "snippet.mp3"
_DEMO_SECONDS = 15.0


def snippet_path() -> Path:
    return _SNIPPET_PATH


@lru_cache(maxsize=8)
def _analyze_snippet_fps(fps: float) -> tuple[AudioBusFrame, ...]:
    path = _SNIPPET_PATH
    if not path.is_file():
        log.warning("demo audio snippet missing at %s", path)
        return tuple()
    analyzer = get_analyzer(AnalyzerKind.STEM)
    frames = analyzer.analyze(path, seek=0.0, duration=_DEMO_SECONDS, fps=fps, beat_tightness=200.0)
    log.info("demo audio: %d frames at %.3f fps from %s", len(frames), fps, path.name)
    return tuple(frames)


def demo_frames_for_fps(fps: float) -> list[AudioBusFrame]:
    return list(_analyze_snippet_fps(fps))


def demo_timeline_for_bus(bus: str, fps: float) -> AudioTimeline:
    """Same snippet frames, keyed by the clip's bus_select (option C)."""
    frames = demo_frames_for_fps(fps)
    if not frames:
        return {}
    return {bus: frames}


async def warmup_demo_audio(fps: float = 30.0) -> None:
    """Load snippet analysis off the event loop (API startup)."""
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, demo_frames_for_fps, fps)
