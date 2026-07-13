"""Load baked preview samples for clip preview bus injection."""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path

from pixfabrica_core.audio.bus import AudioBusFrame, AudioTimeline
from pixfabrica_core.audio.preview_samples import (
    DEFAULT_PREVIEW_SAMPLE_ID,
    PreviewSampleEntry,
    find_web_public,
    load_entry_timeline,
    load_manifest,
    timeline_for_preview,
)

log = logging.getLogger("pixfabrica.api.preview_samples")


def preview_samples_public_root() -> Path:
    env = os.environ.get("PIXFABRICA_PREVIEW_SAMPLES_ROOT")
    if env:
        return Path(env).resolve()
    try:
        return find_web_public()
    except FileNotFoundError:
        return Path(__file__).resolve().parents[2] / "media" / "preview-samples"


@lru_cache(maxsize=1)
def _manifest_samples() -> tuple[PreviewSampleEntry, ...]:
    root = preview_samples_public_root()
    manifest = load_manifest(root)
    return tuple(manifest.samples)


def list_preview_sample_ids() -> list[str]:
    return [s.id for s in _manifest_samples()]


def get_preview_sample(sample_id: str) -> PreviewSampleEntry | None:
    for entry in _manifest_samples():
        if entry.id == sample_id:
            return entry
    return None


@lru_cache(maxsize=64)
def _timeline_for_sample(
    sample_id: str,
    loop_seconds: float,
    fps: float,
) -> tuple[AudioBusFrame, ...]:
    entry = get_preview_sample(sample_id)
    if entry is None:
        log.warning("preview sample not found: %s", sample_id)
        return tuple()
    root = preview_samples_public_root()
    frames = load_entry_timeline(root, entry)
    if not frames:
        log.warning("preview sample timeline missing for %s", sample_id)
        return tuple()
    fitted = timeline_for_preview(
        frames,
        baked_fps=entry.fps,
        loop_seconds=loop_seconds,
        request_fps=fps,
    )
    return tuple(fitted)


def resolve_preview_sample_id(sample_id: str | None) -> str | None:
    if sample_id and sample_id.strip():
        return sample_id.strip()
    if _manifest_samples():
        return DEFAULT_PREVIEW_SAMPLE_ID
    return None


def preview_timeline_for_bus(
    bus: str,
    *,
    sample_id: str | None,
    loop_seconds: float,
    fps: float,
    muted: bool,
) -> AudioTimeline:
    if muted:
        return {}
    resolved = resolve_preview_sample_id(sample_id)
    if not resolved:
        return {}
    frames = list(_timeline_for_sample(resolved, loop_seconds, fps))
    if not frames:
        return {}
    return {bus: frames}


def invalidate_preview_samples_cache() -> None:
    _manifest_samples.cache_clear()
    _timeline_for_sample.cache_clear()
