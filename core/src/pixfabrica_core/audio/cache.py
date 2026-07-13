from __future__ import annotations

import hashlib
import threading
from collections.abc import Callable
from pathlib import Path

from pixfabrica_core.audio.analysis import (
    AnalysisCancelledError,
    AnalyzerKind,
    get_analyzer,
    load_timeline_cache,
    save_timeline_cache,
)
from pixfabrica_core.audio.content_hash import content_sha256_for_path


def timeline_cache_path(
    cache_dir: Path,
    content_sha256: str,
    seek: float,
    duration: float | None,
    fps: float,
    beat_tightness: float,
) -> Path:
    sig = f"{content_sha256}:stem:v2:{seek}:{duration}:{fps}:{beat_tightness}"
    return cache_dir / f"analysis_{hashlib.sha256(sig.encode()).hexdigest()}.npz"


def timeline_cache_path_for_file(
    cache_dir: Path,
    local_path: Path,
    seek: float,
    duration: float | None,
    fps: float,
    beat_tightness: float,
) -> Path:
    content_sha = content_sha256_for_path(local_path)
    return timeline_cache_path(
        cache_dir,
        content_sha,
        seek,
        duration,
        fps,
        beat_tightness,
    )


def analyze_to_cache(
    *,
    cache_dir: Path,
    local_path: Path,
    seek: float,
    duration: float | None,
    fps: float,
    beat_tightness: float,
    on_progress: Callable[[float], None] | None = None,
    cancel: threading.Event | None = None,
) -> Path:
    cache_file = timeline_cache_path_for_file(
        cache_dir,
        local_path,
        seek,
        duration,
        fps,
        beat_tightness,
    )
    if cache_file.exists():
        cached = load_timeline_cache(cache_file)
        if cached:
            if on_progress:
                on_progress(1.0)
            return cache_file

    timeline = get_analyzer(AnalyzerKind.STEM).analyze(
        local_path,
        seek,
        duration,
        fps,
        beat_tightness,
        on_progress=on_progress,
        cancel=cancel,
    )
    if cancel and cancel.is_set():
        raise AnalysisCancelledError

    cache_dir.mkdir(parents=True, exist_ok=True)
    save_timeline_cache(cache_file, timeline)
    return cache_file


def load_cached_timeline(cache_file: Path) -> list:
    return load_timeline_cache(cache_file)
