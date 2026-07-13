"""OpenGL / GPU graph requirements (no moderngl import — probe lives in renderer)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pixfabrica_core.catalog import CatalogCache

GL_UNAVAILABLE_CODE = "gl_unavailable"

# Substrings matched case-insensitively against GL_RENDERER (Mesa llvmpipe, SwiftShader, …).
_SOFTWARE_GL_RENDERER_MARKERS = (
    "llvmpipe",
    "softpipe",
    "swrast",
    "swiftshader",
    "lavapipe",
    "apple software renderer",
    "microsoft basic render",
)


@dataclass(frozen=True, slots=True)
class GlCapability:
    available: bool
    reason: str | None = None
    renderer: str | None = None


def is_software_gl_renderer(renderer: str | None) -> bool:
    """True when GL_RENDERER names a CPU rasterizer, not discrete/integrated GPU."""
    if not renderer or not renderer.strip():
        return False
    lowered = renderer.casefold()
    return any(marker in lowered for marker in _SOFTWARE_GL_RENDERER_MARKERS)


_GL_TRACK_CLIP_TYPES = frozenset({"std-gl-track", "std-post-track"})


def graph_requires_gl_context(graph: dict[str, Any], *, catalog: CatalogCache) -> bool:
    """Return True when this project JSON needs a ModernGL context to render or preview."""
    tracks = graph.get("tracks")
    if not isinstance(tracks, list):
        return False

    gl_clip_types = {clip.clip_type for clip in catalog.clips if clip.track_kind == "gl"}
    gl_effect_types = {fx.effect_type for fx in catalog.effects if fx.effect_backend == "gl"}

    for track in tracks:
        if not isinstance(track, dict) or track.get("enabled") is False:
            continue

        track_type = track.get("clip_type")
        if isinstance(track_type, str) and track_type in _GL_TRACK_CLIP_TYPES:
            return True

        track_kind = track.get("track_kind")
        if isinstance(track_kind, str) and track_kind.strip().lower() in ("gl", "post"):
            return True

        track_type_ui = track.get("trackType")
        if isinstance(track_type_ui, str) and track_type_ui.strip().lower() in ("gl", "post"):
            return True

        clips = track.get("clips")
        if not isinstance(clips, list):
            continue

        for clip in clips:
            if not isinstance(clip, dict) or clip.get("enabled") is False:
                continue

            clip_type = clip.get("clip_type")
            if isinstance(clip_type, str) and clip_type in gl_clip_types:
                return True

            effects = clip.get("effects")
            if not isinstance(effects, list):
                continue

            for effect in effects:
                if not isinstance(effect, dict) or effect.get("enabled") is False:
                    continue
                fx_type = effect.get("effect_type")
                if isinstance(fx_type, str) and fx_type in gl_effect_types:
                    return True

    return False
