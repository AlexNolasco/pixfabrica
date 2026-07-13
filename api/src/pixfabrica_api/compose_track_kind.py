"""Track kind constraints for compose (skia / gl / post)."""

from __future__ import annotations

from typing import Any

from pixfabrica_api.catalog_cache import get_catalog_cache
from pixfabrica_api.compose_catalog import get_clip_detail_for_compose
from pixfabrica_core.clips import RenderJob

TRACK_KIND_TO_TRACK_TYPE: dict[str, str] = {
    "skia": "std-skia-track",
    "gl": "std-gl-track",
    "post": "std-post-track",
}

TRACK_TYPE_TO_KIND: dict[str, str] = {
    track_type: kind for kind, track_type in TRACK_KIND_TO_TRACK_TYPE.items()
}


def clip_track_kind(clip_type: str) -> str | None:
    """Catalog track_kind for a clip_type, if known."""
    detail = get_clip_detail_for_compose(clip_type)
    if not detail.get("ok"):
        return None
    kind = detail.get("track_kind")
    return kind if isinstance(kind, str) else None


def assert_clip_matches_track_kind(
    *,
    clip_type: str,
    track_kind: str,
    track_index: int,
    clip_index: int,
) -> None:
    expected = clip_track_kind(clip_type)
    if expected is None:
        return
    if expected != track_kind:
        raise ValueError(
            f"track {track_index} clip {clip_index}: {clip_type} belongs on "
            f"{expected} tracks only (track_kind={expected!r}, got {track_kind!r})"
        )


def _clip_type_of(clip: Any) -> str:
    clip_type = getattr(type(clip), "clip_type", None)
    if isinstance(clip_type, str) and clip_type:
        return clip_type
    raw = getattr(clip, "clip_type", None)
    return raw if isinstance(raw, str) else ""


def _track_kind_for_track(track: Any) -> str | None:
    track_type = getattr(type(track), "clip_type", None)
    if isinstance(track_type, str):
        return TRACK_TYPE_TO_KIND.get(track_type)
    return None


def track_kind_errors_for_graph(graph: dict[str, Any]) -> list[str]:
    """Validate track_kind placement on raw project JSON (pre-RenderJob)."""
    tracks = graph.get("tracks")
    if not isinstance(tracks, list):
        return []

    errors: list[str] = []
    for track_index, track in enumerate(tracks):
        if not isinstance(track, dict):
            continue
        track_type = track.get("clip_type")
        if not isinstance(track_type, str):
            track_kind_raw = track.get("track_kind")
            if isinstance(track_kind_raw, str):
                track_kind = track_kind_raw.strip().lower()
            else:
                continue
        else:
            track_kind = TRACK_TYPE_TO_KIND.get(track_type)
        if track_kind is None:
            continue

        track_id = track.get("id", f"track-{track_index}")
        clips = track.get("clips")
        if not isinstance(clips, list):
            continue
        for clip in clips:
            if not isinstance(clip, dict):
                continue
            clip_type = clip.get("clip_type")
            if not isinstance(clip_type, str) or not clip_type.strip():
                continue
            clip_type = clip_type.strip()
            expected = clip_track_kind(clip_type)
            if expected is None or expected == track_kind:
                continue
            errors.append(
                f"track {track_id}: {clip_type} requires {expected} tracks only, not {track_kind}"
            )
    return errors


def track_kind_errors_for_job(job: RenderJob) -> list[str]:
    """Return hard errors when clips sit on the wrong track backend."""
    cache = get_catalog_cache()
    kind_by_clip: dict[str, str] = {row.clip_type: row.track_kind for row in cache.clips}
    for effect in cache.effects:
        kind_by_clip[effect.effect_type] = "post"

    errors: list[str] = []
    for track in job.tracks:
        track_kind = _track_kind_for_track(track)
        if track_kind is None:
            continue
        track_id = getattr(track, "id", "?")
        for clip in track.clips:
            clip_type = _clip_type_of(clip)
            if not clip_type:
                continue
            expected = kind_by_clip.get(clip_type)
            if expected is None or expected == track_kind:
                continue
            errors.append(
                f"track {track_id}: {clip_type} requires {expected} tracks only, not {track_kind}"
            )
    return errors
