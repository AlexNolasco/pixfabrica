"""Read-only server policy and capability limits for the web client."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from pixfabrica_api.catalog_config import catalog_policy_payload
from pixfabrica_api.gl_policy import gl_capability_payload
from pixfabrica_api.pexels_settings import (
    pexels_available,
    pexels_default_queries,
    pexels_default_video_queries,
)
from pixfabrica_api.server_config import (
    DEFAULT_LOCALE,
    MAX_CLIPS_PER_TRACK,
    MAX_DURATION_S,
    MAX_FPS,
    MAX_HEIGHT,
    MAX_PREVIEW_LONG_SIDE,
    MAX_TRACKS,
    MAX_WIDTH,
    upload_limits_payload,
)

router = APIRouter(tags=["config"])


class ServerCapabilitiesResponse(BaseModel):
    gl_available: bool = Field(description="Whether a standalone OpenGL context can be created")
    gl_reason: str | None = Field(default=None, description="Probe failure reason when unavailable")
    gl_renderer: str | None = Field(default=None, description="GL_RENDERER when available")


class CatalogPolicyResponse(BaseModel):
    excluded_licenses: list[str] = Field(
        default_factory=list,
        description="SPDX license ids excluded from the active catalog on this host",
    )


class ServerConfigResponse(BaseModel):
    max_preview_long_side: int = Field(description="Longest preview frame axis in pixels")
    max_duration_s: int = Field(description="Max project duration in seconds")
    max_width: int = Field(description="Max project frame width in pixels")
    max_height: int = Field(description="Max project frame height in pixels")
    max_fps: int = Field(description="Max project frame rate")
    max_tracks: int = Field(
        description="Max timeline rows (visual tracks + audio buses combined)",
    )
    max_clips_per_track: int = Field(description="Max clips per visual track")
    upload_limits: dict[str, int] = Field(
        description="Max upload size in bytes per media kind",
    )
    capabilities: ServerCapabilitiesResponse = Field(
        description="Host runtime capabilities for the web client",
    )
    pexels_default_queries: list[str] = Field(
        default_factory=list,
        description="Quick-pick Pexels search tags when stock photos are configured",
    )
    pexels_default_video_queries: list[str] = Field(
        default_factory=list,
        description="Quick-pick Pexels search tags when stock videos are configured",
    )
    catalog: CatalogPolicyResponse = Field(
        description="Host catalog policy for the web client",
    )
    default_locale: str = Field(
        description="Deployment default BCP-47 locale for first-visit UI and API lang fallbacks",
    )


@router.get("/config", response_model=ServerConfigResponse)
async def get_config() -> ServerConfigResponse:
    gl = gl_capability_payload()
    return ServerConfigResponse(
        max_preview_long_side=MAX_PREVIEW_LONG_SIDE,
        max_duration_s=MAX_DURATION_S,
        max_width=MAX_WIDTH,
        max_height=MAX_HEIGHT,
        max_fps=MAX_FPS,
        max_tracks=MAX_TRACKS,
        max_clips_per_track=MAX_CLIPS_PER_TRACK,
        upload_limits=upload_limits_payload(),
        capabilities=ServerCapabilitiesResponse(
            gl_available=bool(gl.get("gl_available")),
            gl_reason=gl.get("gl_reason"),
            gl_renderer=gl.get("gl_renderer"),
        ),
        pexels_default_queries=list(pexels_default_queries()) if pexels_available() else [],
        pexels_default_video_queries=list(pexels_default_video_queries())
        if pexels_available()
        else [],
        catalog=CatalogPolicyResponse(**catalog_policy_payload()),
        default_locale=DEFAULT_LOCALE,
    )
