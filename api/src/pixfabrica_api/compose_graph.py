"""Graph validation helpers for the compose agent."""

from __future__ import annotations

from typing import Any

from pixfabrica_api.compose_layout_lints import compose_layout_lints
from pixfabrica_api.compose_track_kind import track_kind_errors_for_graph, track_kind_errors_for_job
from pixfabrica_api.gl_policy import gl_graph_violation
from pixfabrica_api.license_policy import license_graph_violation
from pixfabrica_api.plugin_registry import ensure_plugins_registered
from pixfabrica_api.project_limits import graph_policy_violation
from pixfabrica_core.clips import RenderJob
from pixfabrica_core.composition.unknown import UnknownClip


def unknown_clip_types(job: RenderJob) -> list[str]:
    unknown: list[str] = []
    for track in job.tracks:
        for clip in track.clips:
            if isinstance(clip, UnknownClip):
                unknown.append(clip.raw_clip_type or "<missing clip_type>")
    return unknown


def validate_graph_for_compose(graph: dict[str, Any]) -> dict[str, Any]:
    """Validate a web/render job graph for compose tools (no HTTP exceptions)."""
    ensure_plugins_registered()

    policy_err = graph_policy_violation(graph)
    if policy_err is not None:
        return {
            "ok": False,
            "code": policy_err["code"],
            "errors": [policy_err["detail"]],
        }

    track_kind_errors = track_kind_errors_for_graph(graph)
    if track_kind_errors:
        return {"ok": False, "errors": track_kind_errors}

    gl_err = gl_graph_violation(graph)
    if gl_err is not None:
        return {"ok": False, "code": gl_err["code"], "errors": [gl_err["detail"]]}

    license_err = license_graph_violation(graph)
    if license_err is not None:
        return {"ok": False, "code": license_err["code"], "errors": [license_err["detail"]]}

    try:
        job = RenderJob.model_validate(graph)
    except Exception as exc:
        return {"ok": False, "errors": [str(exc)]}

    unknown_types = unknown_clip_types(job)
    if unknown_types:
        joined = ", ".join(sorted(set(unknown_types)))
        return {"ok": False, "errors": [f"unknown clip type(s): {joined}"]}

    track_kind_errors = track_kind_errors_for_job(job)
    if track_kind_errors:
        return {"ok": False, "errors": track_kind_errors}

    warnings, hints = compose_layout_lints(job)
    result: dict[str, Any] = {
        "ok": True,
        "title": job.title,
        "track_count": len(job.tracks),
        "sound_count": len(job.sounds),
        "duration": job.duration,
    }
    if warnings:
        result["warnings"] = warnings
    if hints:
        result["hints"] = hints
    return result
