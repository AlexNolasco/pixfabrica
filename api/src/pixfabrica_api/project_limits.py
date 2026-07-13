"""Hosted API timeline policy — not enforced in core or renderer."""

from __future__ import annotations

import math
from typing import Any, NotRequired, TypedDict, cast

from fastapi import HTTPException

from pixfabrica_api.server_config import (
    MAX_CLIPS_PER_TRACK,
    MAX_DURATION_S,
    MAX_FPS,
    MAX_HEIGHT,
    MAX_TRACKS,
    MAX_WIDTH,
)


class LimitErrorPayload(TypedDict):
    code: str
    max: int
    actual: int
    detail: str
    track_index: NotRequired[int]


def limit_error_payload(
    code: str,
    *,
    max_val: int,
    actual: int,
    detail: str,
    track_index: int | None = None,
) -> LimitErrorPayload:
    payload: LimitErrorPayload = {
        "code": code,
        "max": max_val,
        "actual": actual,
        "detail": detail,
    }
    if track_index is not None:
        payload["track_index"] = track_index
    return payload


def _validate_render_limits(graph_data: dict[str, Any]) -> None:
    """Duration → width → height → fps (inclusive max)."""
    raw_duration = graph_data.get("duration")
    if raw_duration is not None:
        try:
            duration = float(raw_duration)
        except (TypeError, ValueError):
            duration = -1.0
        if duration > MAX_DURATION_S:
            actual = int(math.ceil(duration))
            raise HTTPException(
                status_code=422,
                detail=limit_error_payload(
                    "limit_duration_exceeded",
                    max_val=MAX_DURATION_S,
                    actual=actual,
                    detail=(f"Project duration is {duration:g}s; max is {MAX_DURATION_S}s"),
                ),
            )

    raw_width = graph_data.get("width")
    if raw_width is not None:
        try:
            width = int(raw_width)
        except (TypeError, ValueError):
            width = MAX_WIDTH + 1
        if width > MAX_WIDTH:
            raise HTTPException(
                status_code=422,
                detail=limit_error_payload(
                    "limit_width_exceeded",
                    max_val=MAX_WIDTH,
                    actual=width,
                    detail=f"Project width is {width}px; max is {MAX_WIDTH}px",
                ),
            )

    raw_height = graph_data.get("height")
    if raw_height is not None:
        try:
            height = int(raw_height)
        except (TypeError, ValueError):
            height = MAX_HEIGHT + 1
        if height > MAX_HEIGHT:
            raise HTTPException(
                status_code=422,
                detail=limit_error_payload(
                    "limit_height_exceeded",
                    max_val=MAX_HEIGHT,
                    actual=height,
                    detail=f"Project height is {height}px; max is {MAX_HEIGHT}px",
                ),
            )

    raw_fps = graph_data.get("fps")
    if raw_fps is not None:
        try:
            fps = float(raw_fps)
        except (TypeError, ValueError):
            fps = MAX_FPS + 1.0
        if fps > MAX_FPS:
            actual = int(math.ceil(fps))
            raise HTTPException(
                status_code=422,
                detail=limit_error_payload(
                    "limit_fps_exceeded",
                    max_val=MAX_FPS,
                    actual=actual,
                    detail=f"Project fps is {fps:g}; max is {MAX_FPS}",
                ),
            )


def validate_graph_policy(graph_data: dict[str, Any]) -> None:
    """Raise HTTPException when graph exceeds hosted timeline policy."""
    _validate_render_limits(graph_data)

    tracks_raw = graph_data.get("tracks") or []
    sounds_raw = graph_data.get("sounds") or []
    if not isinstance(tracks_raw, list) or not isinstance(sounds_raw, list):
        return

    row_count = len(tracks_raw) + len(sounds_raw)
    if row_count > MAX_TRACKS:
        raise HTTPException(
            status_code=422,
            detail=limit_error_payload(
                "limit_tracks_exceeded",
                max_val=MAX_TRACKS,
                actual=row_count,
                detail=(
                    f"Graph has {row_count} timeline rows (tracks + audio buses);"
                    f" max is {MAX_TRACKS}"
                ),
            ),
        )

    for i, track in enumerate(tracks_raw):
        if not isinstance(track, dict):
            continue
        clips = track.get("clips") or []
        if not isinstance(clips, list):
            continue
        count = len(clips)
        if count > MAX_CLIPS_PER_TRACK:
            raise HTTPException(
                status_code=422,
                detail=limit_error_payload(
                    "limit_clips_per_track_exceeded",
                    max_val=MAX_CLIPS_PER_TRACK,
                    actual=count,
                    detail=(f"Track index {i} has {count} clips; max is {MAX_CLIPS_PER_TRACK}"),
                    track_index=i,
                ),
            )


def graph_policy_violation(graph_data: dict[str, Any]) -> LimitErrorPayload | None:
    """Return a limit error payload, or None when within policy."""
    try:
        validate_graph_policy(graph_data)
    except HTTPException as exc:
        detail = exc.detail
        if isinstance(detail, dict):
            return cast(LimitErrorPayload, detail)
        return limit_error_payload(
            "limit_policy_violation",
            max_val=0,
            actual=0,
            detail=str(detail),
        )
    return None
