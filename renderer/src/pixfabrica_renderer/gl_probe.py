"""Probe host OpenGL availability via ModernGL (cached per process)."""

from __future__ import annotations

import os
from typing import Any

from pixfabrica_core.capabilities.gl import GlCapability, is_software_gl_renderer

_cached: GlCapability | None = None
_ENV_GL_BACKEND = "PIXFABRICA_GL_BACKEND"


def _probe_disabled_by_env() -> bool:
    raw = os.environ.get("PIXFABRICA_GL_PROBE", "1").strip().lower()
    return raw in ("0", "false", "no", "off")


def _apply_egl_env() -> None:
    """Headless EGL setup (Docker, no X11). Safe to call repeatedly."""
    os.environ.setdefault("PYOPENGL_PLATFORM", "egl")
    os.environ.setdefault("EGL_PLATFORM", "surfaceless")


def create_standalone_gl_context(**kwargs: Any):
    """Create a standalone ModernGL context (EGL in headless/GPU containers, else GLX)."""
    import moderngl

    backend = os.environ.get(_ENV_GL_BACKEND, "auto").strip().lower()
    if backend == "egl":
        backends: list[str | None] = ["egl"]
    elif backend in ("glx", "default"):
        backends = [None]
    else:
        # Headless containers have no X display; EGL first avoids XOpenDisplay noise.
        backends = ["egl", None]

    last_exc: Exception | None = None
    for item in backends:
        try:
            if item == "egl":
                _apply_egl_env()
                egl_kwargs: dict[str, Any] = {"backend": "egl", **kwargs}
                return moderngl.create_standalone_context(**egl_kwargs)
            return moderngl.create_standalone_context(**kwargs)
        except Exception as exc:
            last_exc = exc
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("no GL backend configured")


def reset_gl_probe_cache() -> None:
    """Clear cached probe result (tests only)."""
    global _cached
    _cached = None


def probe_gl_available(*, force: bool = False) -> GlCapability:
    """Try to create a standalone ModernGL context; cache the outcome."""
    global _cached
    if _probe_disabled_by_env():
        return GlCapability(available=True, reason="probe_disabled")
    if _cached is not None and not force:
        return _cached

    try:
        ctx = create_standalone_gl_context()
        info = getattr(ctx, "info", {}) or {}
        renderer = info.get("GL_RENDERER") if isinstance(info, dict) else None
        renderer_str = str(renderer) if renderer else None
        ctx.release()
        if is_software_gl_renderer(renderer_str):
            _cached = GlCapability(
                available=False,
                reason="software_gl_renderer",
                renderer=renderer_str,
            )
        else:
            _cached = GlCapability(
                available=True,
                renderer=renderer_str,
            )
    except Exception as exc:
        _cached = GlCapability(available=False, reason=str(exc))

    return _cached


def gl_available() -> bool:
    return probe_gl_available().available
