"""Build RenderJob-shaped graphs from compact compose specs."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from pixfabrica_api.compose_catalog import get_clip_detail_for_compose
from pixfabrica_api.compose_track_kind import (
    TRACK_KIND_TO_TRACK_TYPE,
    assert_clip_matches_track_kind,
)


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:8]}"


def _merge_clip(
    *,
    clip_type: str,
    params: dict[str, Any] | None,
    start: float,
    clip_index: int,
) -> dict[str, Any]:
    detail = get_clip_detail_for_compose(clip_type)
    if not detail.get("ok"):
        errors = detail.get("errors") or [f"unknown clip type: {clip_type}"]
        raise ValueError(errors[0])

    defaults = detail.get("defaults")
    if not isinstance(defaults, dict):
        defaults = {}

    merged: dict[str, Any] = {**defaults}
    if params:
        merged.update(params)

    clip: dict[str, Any] = {
        "clip_type": clip_type,
        "id": _new_id("el"),
        "start": start,
        **merged,
    }
    return clip


def build_graph_from_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Expand a compact compose spec into web/render project JSON."""
    title = str(spec.get("title") or "Untitled").strip() or "Untitled"
    description = str(spec.get("description") or "").strip()
    duration = float(spec.get("duration") or 10.0)
    width = int(spec.get("width") or 1280)
    height = int(spec.get("height") or 720)
    fps = float(spec.get("fps") or 24.0)

    tracks_raw = spec.get("tracks")
    if not isinstance(tracks_raw, list) or not tracks_raw:
        raise ValueError("tracks must be a non-empty array")

    tracks: list[dict[str, Any]] = []
    for track_index, track_raw in enumerate(tracks_raw):
        if not isinstance(track_raw, dict):
            raise ValueError(f"track {track_index} must be an object")
        track_kind = str(track_raw.get("track_kind") or "").strip().lower()
        track_type = TRACK_KIND_TO_TRACK_TYPE.get(track_kind)
        if track_type is None:
            known = ", ".join(sorted(TRACK_KIND_TO_TRACK_TYPE))
            raise ValueError(f"track {track_index}: track_kind must be one of {known}")

        clips_raw = track_raw.get("clips")
        if not isinstance(clips_raw, list) or not clips_raw:
            raise ValueError(f"track {track_index} must include a non-empty clips array")

        clips: list[dict[str, Any]] = []
        for clip_index, clip_raw in enumerate(clips_raw):
            if not isinstance(clip_raw, dict):
                raise ValueError(f"track {track_index} clip {clip_index} must be an object")
            clip_type = str(
                clip_raw.get("clip_type") or "",
            ).strip()
            if not clip_type:
                raise ValueError(f"track {track_index} clip {clip_index} missing clip_type")
            assert_clip_matches_track_kind(
                clip_type=clip_type,
                track_kind=track_kind,
                track_index=track_index,
                clip_index=clip_index,
            )
            params = clip_raw.get("params")
            if params is not None and not isinstance(params, dict):
                raise ValueError(f"track {track_index} clip {clip_index} params must be an object")
            start = float(clip_raw.get("start") or 0.0)
            clips.append(
                _merge_clip(
                    clip_type=clip_type,
                    params=params,
                    start=start,
                    clip_index=clip_index,
                )
            )

        track: dict[str, Any] = {
            "clip_type": track_type,
            "id": _new_id("track"),
            "start": float(track_raw.get("start") or 0.0),
            "clips": clips,
        }
        if (transition_in := track_raw.get("transition_in")) and isinstance(transition_in, dict):
            track["transition_in"] = transition_in
        if (transition_out := track_raw.get("transition_out")) and isinstance(transition_out, dict):
            track["transition_out"] = transition_out
        tracks.append(track)

    return {
        "title": title,
        "description": description,
        "width": width,
        "height": height,
        "fps": fps,
        "duration": duration,
        "tracks": tracks,
    }
