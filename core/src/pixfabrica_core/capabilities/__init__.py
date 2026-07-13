"""Runtime capability helpers shared across API, CLI, and renderer."""

from pixfabrica_core.capabilities.gl import (
    GL_UNAVAILABLE_CODE,
    GlCapability,
    graph_requires_gl_context,
)

__all__ = [
    "GL_UNAVAILABLE_CODE",
    "GlCapability",
    "graph_requires_gl_context",
]
