"""Hosted API policy for OpenGL-dependent projects."""

from __future__ import annotations

from typing import Any, TypedDict

from fastapi import HTTPException

from pixfabrica_api.catalog_cache import get_catalog_cache
from pixfabrica_core.capabilities.gl import GL_UNAVAILABLE_CODE, graph_requires_gl_context
from pixfabrica_renderer.gl_probe import gl_available, probe_gl_available


class GlPolicyErrorPayload(TypedDict):
    code: str
    detail: str


_GL_UNAVAILABLE_DETAIL = (
    "This project uses GL tracks or GPU effects, but OpenGL is not available on this host."
)

_SOFTWARE_GL_DETAIL = (
    "This project uses GL tracks or GPU effects, but this host only exposes a software"
    " OpenGL renderer (CPU). A GPU is required."
)


def gl_capability_payload() -> dict[str, Any]:
    cap = probe_gl_available()
    payload: dict[str, Any] = {"gl_available": cap.available}
    if cap.reason:
        payload["gl_reason"] = cap.reason
    if cap.renderer:
        payload["gl_renderer"] = cap.renderer
    return payload


def gl_graph_violation(graph_data: dict[str, Any]) -> GlPolicyErrorPayload | None:
    """Return a policy error payload when GL is required but unavailable."""
    if gl_available():
        return None
    cap = probe_gl_available()
    catalog = get_catalog_cache()
    if not graph_requires_gl_context(graph_data, catalog=catalog):
        return None
    detail = _SOFTWARE_GL_DETAIL if cap.reason == "software_gl_renderer" else _GL_UNAVAILABLE_DETAIL
    return GlPolicyErrorPayload(code=GL_UNAVAILABLE_CODE, detail=detail)


def validate_graph_gl_policy(graph_data: dict[str, Any]) -> None:
    """Raise HTTPException when the graph needs GL but the host cannot provide it."""
    violation = gl_graph_violation(graph_data)
    if violation is not None:
        raise HTTPException(status_code=422, detail=violation)
