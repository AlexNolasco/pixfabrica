"""Readability / layout heuristics for compose validate_graph."""

from __future__ import annotations

from typing import Any

from pixfabrica_api.compose_typography import lint_typography_roles
from pixfabrica_core.clips import ClipCategory, RenderJob

_OFFSET_EPS = 0.08
_TIME_EPS = 0.05
_COMPOSITOR_TRACK_TYPES = frozenset({"std-skia-track", "std-gl-track"})


def _track_clip_type(track: Any) -> str:
    return str(getattr(type(track), "clip_type", "") or "")


def _clip_type_of(clip: Any) -> str:
    return str(getattr(type(clip), "clip_type", "") or getattr(clip, "clip_type", ""))


def _is_text_clip(clip: Any) -> bool:
    return getattr(type(clip), "clip_category", None) == ClipCategory.TEXT


def _clip_offsets(clip: Any) -> tuple[float, float] | None:
    ox = getattr(clip, "offset_x", None)
    oy = getattr(clip, "offset_y", None)
    if isinstance(ox, (int, float)) and isinstance(oy, (int, float)):
        return float(ox), float(oy)
    return None


def _clip_time_range(clip: Any) -> tuple[float, float]:
    start = float(getattr(clip, "start", 0.0) or 0.0)
    duration = getattr(clip, "duration", None)
    if isinstance(duration, (int, float)) and duration > 0:
        return start, start + float(duration)
    return start, float("inf")


def _offsets_overlap(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return abs(a[0] - b[0]) <= _OFFSET_EPS and abs(a[1] - b[1]) <= _OFFSET_EPS


def _times_overlap(a: tuple[float, float], b: tuple[float, float]) -> bool:
    latest_start = max(a[0], b[0])
    earliest_end = min(a[1], b[1])
    return latest_start + _TIME_EPS < earliest_end


def _track_has_transition(track: Any) -> bool:
    return (
        getattr(track, "transition_in", None) is not None
        or getattr(track, "transition_out", None) is not None
    )


def compose_layout_lints(job: RenderJob) -> tuple[list[str], list[str]]:
    """Return (warnings, hints) for kidbashing readability."""
    warnings: list[str] = []
    hints: list[str] = []

    compositor_tracks = [
        track
        for track in job.tracks
        if _track_clip_type(track) in _COMPOSITOR_TRACK_TYPES and getattr(track, "enabled", True)
    ]

    zero_start_tracks = [
        t for t in compositor_tracks if abs(float(getattr(t, "start", 0.0))) <= _TIME_EPS
    ]
    if len(zero_start_tracks) > 1:
        ids = ", ".join(getattr(t, "id", _track_clip_type(t)) for t in zero_start_tracks)
        warnings.append(
            f"{len(zero_start_tracks)} full-frame tracks start at 0 ({ids}) — scenes stack and compete"
        )
        hints.append(
            "Stagger track.start (one scene at a time) or use transition_in/out for intentional crossfades"
        )

    if len(compositor_tracks) > 1:
        starts = sorted(float(getattr(t, "start", 0.0)) for t in compositor_tracks)
        if len(starts) >= 2 and all(abs(s - starts[0]) <= _TIME_EPS for s in starts):
            warnings.append(
                "All compositor tracks share the same start — no temporal gap between scenes"
            )
            hints.append(
                "Set later tracks to start after earlier ones finish (minus transition overlap)"
            )

    for track in compositor_tracks:
        track_id = getattr(track, "id", _track_clip_type(track))
        text_clips = [
            el for el in track.clips if _is_text_clip(el) and getattr(el, "enabled", True)
        ]
        if len(text_clips) < 2:
            continue

        for i, left in enumerate(text_clips):
            left_off = _clip_offsets(left)
            if left_off is None:
                continue
            left_range = _clip_time_range(left)
            for right in text_clips[i + 1 :]:
                right_off = _clip_offsets(right)
                if right_off is None:
                    continue
                if not _offsets_overlap(left_off, right_off):
                    continue
                if not _times_overlap(left_range, _clip_time_range(right)):
                    continue
                warnings.append(
                    f"track {track_id}: text clips {_clip_type_of(left)} and "
                    f"{_clip_type_of(right)} overlap at offset "
                    f"({left_off[0]:.2f}, {left_off[1]:.2f}) — likely unreadable"
                )
                hints.append(
                    "Separate text vertically (e.g. title offset_y 0.35, subtitle 0.65) "
                    "or use staggered tracks"
                )

        hero_text = [el for el in text_clips if _clip_offsets(el) is not None]
        if len(hero_text) > 2:
            warnings.append(
                f"track {track_id}: {len(hero_text)} text clips — prefer one hero line per scene"
            )
            hints.append("Keep one primary text; move extras to another track or drop them")

        role_warnings, role_hints = lint_typography_roles(text_clips, str(track_id))
        warnings.extend(role_warnings)
        hints.extend(role_hints)

    # Deduplicate while preserving order
    def _unique(items: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for item in items:
            if item in seen:
                continue
            seen.add(item)
            out.append(item)
        return out

    return _unique(warnings), _unique(hints)
