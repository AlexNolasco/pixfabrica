"""Preview reprepare scope — which subgraphs need work when the graph changes."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Any

from pixfabrica_core.clips import RenderJob
from pixfabrica_core.composition.track import GLEffectTrack, GLTrack, TrackClip


class ReprepareScope(StrEnum):
    """How much of a preview session compositor to rebuild."""

    FULL = "full"
    SKIP_AUDIO = "skip_audio"
    GL_CONTEXT_ONLY = "gl_context_only"


def _stable_hash(payload: Any) -> str:
    return hashlib.md5(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _bus_wiring_snapshot(graph_data: dict[str, Any]) -> list[dict[str, str]]:
    """Explicit visual ``bus_select`` values — drives preview sound prepare."""
    wiring: list[dict[str, str]] = []
    for track in graph_data.get("tracks") or []:
        if not isinstance(track, dict) or track.get("enabled") is False:
            continue
        for clip in track.get("clips") or []:
            if not isinstance(clip, dict) or clip.get("enabled") is False:
                continue
            raw = clip.get("bus_select")
            if not isinstance(raw, str) or not raw.strip():
                continue
            wiring.append(
                {
                    "id": str(clip.get("id") or ""),
                    "bus_select": raw.strip(),
                }
            )
    wiring.sort(key=lambda row: row["id"])
    return wiring


def _effect_bus_wiring_snapshot(graph_data: dict[str, Any]) -> list[dict[str, str | float]]:
    """Bus-active effect wiring — mirrors ``preview_bus_names_needed_by_visuals``."""
    wiring: list[dict[str, str | float]] = []
    for track in graph_data.get("tracks") or []:
        if not isinstance(track, dict) or track.get("enabled") is False:
            continue
        for clip in track.get("clips") or []:
            if not isinstance(clip, dict) or clip.get("enabled") is False:
                continue
            clip_id = str(clip.get("id") or "")
            for effect in clip.get("effects") or []:
                if not isinstance(effect, dict) or effect.get("enabled") is False:
                    continue
                if "bus_select" not in effect and "sensitivity" not in effect:
                    continue
                sensitivity_raw = effect.get("sensitivity", 0.0)
                sensitivity = (
                    float(sensitivity_raw) if isinstance(sensitivity_raw, (int, float)) else 0.0
                )
                raw_bus = effect.get("bus_select")
                bus_select = raw_bus.strip() if isinstance(raw_bus, str) else ""
                has_bus = bool(bus_select)
                if sensitivity <= 0.0 and not has_bus:
                    continue
                wiring.append(
                    {
                        "clip_id": clip_id,
                        "id": str(effect.get("id") or ""),
                        "bus_select": bus_select,
                        "sensitivity": sensitivity,
                    }
                )
    wiring.sort(key=lambda row: (str(row["clip_id"]), str(row["id"])))
    return wiring


def preview_audio_prepare_hash(graph_data: dict[str, Any]) -> str:
    """Hash of inputs that affect preview sound ``prepare()`` and bus timelines."""
    return _stable_hash(
        {
            "sounds": graph_data.get("sounds") or [],
            "fps": graph_data.get("fps"),
            "duration": graph_data.get("duration"),
            "bus_wiring": _bus_wiring_snapshot(graph_data),
            "effect_bus_wiring": _effect_bus_wiring_snapshot(graph_data),
        }
    )


def resolve_reprepare_scope(
    *,
    graph_changed: bool,
    force_reprepare: bool,
    audio_hash_changed: bool,
    uses_gl: bool,
) -> ReprepareScope:
    """Pick the narrowest safe reprepare scope for a preview session."""
    if force_reprepare and not graph_changed and uses_gl:
        return ReprepareScope.GL_CONTEXT_ONLY
    if not audio_hash_changed and (graph_changed or force_reprepare):
        return ReprepareScope.SKIP_AUDIO
    return ReprepareScope.FULL


def job_uses_gl_tracks(job: RenderJob) -> bool:
    return any(isinstance(track, (GLTrack, GLEffectTrack)) for track in job.tracks)


def track_content_hash(track: TrackClip) -> str:
    return _stable_hash(track.model_dump(mode="json"))


def merge_tracks_preserving_skia(
    new_tracks: list[TrackClip],
    old_tracks: list[TrackClip],
) -> tuple[list[TrackClip], list[TrackClip]]:
    """Reuse prepared Skia tracks when content is unchanged; always take new GL tracks.

    Returns ``(merged_tracks, tracks_to_prepare)``.
    """
    old_skia = {t.id: t for t in old_tracks if not isinstance(t, (GLTrack, GLEffectTrack))}
    old_hashes = {tid: track_content_hash(t) for tid, t in old_skia.items()}

    merged: list[TrackClip] = []
    to_prepare: list[TrackClip] = []

    for track in new_tracks:
        if isinstance(track, (GLTrack, GLEffectTrack)):
            merged.append(track)
            to_prepare.append(track)
            continue

        old = old_skia.get(track.id)
        if old is not None and old_hashes.get(track.id) == track_content_hash(track):
            merged.append(old)
            continue

        merged.append(track)
        to_prepare.append(track)

    return merged, to_prepare


def tracks_needing_prepare(
    job: RenderJob,
    *,
    scope: ReprepareScope,
    old_tracks: list[TrackClip] | None,
) -> tuple[list[TrackClip], list[TrackClip]]:
    """Resolve compositor track list and which tracks need ``prepare()``."""
    if scope == ReprepareScope.GL_CONTEXT_ONLY and old_tracks is not None:
        return merge_tracks_preserving_skia(job.tracks, old_tracks)
    return job.tracks, list(job.tracks)
