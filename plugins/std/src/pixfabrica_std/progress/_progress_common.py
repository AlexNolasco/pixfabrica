"""Shared progress-bar timing and track layout helpers."""

from __future__ import annotations

from typing import Literal

from pixfabrica_core.graphics import Rect

TimeMode = Literal["clip", "job"]
TimeFormat = Literal["mm:ss", "h:mm:ss"]
CounterDirection = Literal["forward", "backward"]
TrackAnchor = Literal["left", "center", "right"]


def track_layout(
    bounds: Rect,
    *,
    offset_x: float,
    width: float,
    anchor_x: TrackAnchor = "center",
) -> tuple[float, float, float, float] | None:
    """Return ``(track_x, track_y, track_w, bounds_h)`` in canvas space."""
    w, h = float(bounds.width), float(bounds.height)
    width_frac = max(0.0, min(float(width), 1.0))
    if width_frac <= 0.0:
        return None

    track_w = width_frac * w
    anchor_px = float(bounds.x) + min(max(float(offset_x), 0.0), 1.0) * w

    match anchor_x:
        case "left":
            track_x = anchor_px
        case "right":
            track_x = anchor_px - track_w
        case _:
            track_x = anchor_px - track_w / 2.0

    left = float(bounds.x)
    right = left + w
    track_x = max(left, min(track_x, right - track_w))
    return track_x, float(bounds.y), track_w, h


def playback_times(
    *,
    time_t: float,
    start: float,
    duration: float | None,
    job_duration: float,
    time_mode: TimeMode,
) -> tuple[float, float, float]:
    """Return ``(elapsed, span, progress)`` clamped to the active window."""
    if time_mode == "job":
        span = max(float(job_duration), 1e-6)
        elapsed = max(0.0, min(float(time_t), span))
        progress = min(max(float(time_t), 0.0) / span, 1.0)
        return elapsed, span, progress

    span = max(float(duration if duration is not None else job_duration), 1e-6)
    local_t = max(0.0, float(time_t) - float(start))
    elapsed = min(local_t, span)
    progress = min(local_t / span, 1.0)
    return elapsed, span, progress


def format_progress_time(seconds: float) -> str:
    """Render scrubber time as ``mm:ss`` or ``h:mm:ss`` when >= 1 hour."""
    total = max(0, int(round(seconds)))
    hours = total // 3600
    minutes = (total % 3600) // 60
    secs = total % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def format_counter_time(seconds: float, time_format: TimeFormat) -> str:
    """Render counter time with a fixed format (no auto-switching)."""
    total = max(0, int(round(seconds)))
    if time_format == "h:mm:ss":
        hours = total // 3600
        minutes = (total % 3600) // 60
        secs = total % 60
        return f"{hours}:{minutes:02d}:{secs:02d}"
    minutes = total // 60
    secs = total % 60
    return f"{minutes:02d}:{secs:02d}"


def counter_display_seconds(
    elapsed: float,
    span: float,
    direction: CounterDirection,
) -> float:
    """Return the seconds value shown for the chosen counter direction."""
    if direction == "backward":
        return max(0.0, span - elapsed)
    return elapsed
