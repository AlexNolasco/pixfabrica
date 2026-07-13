"""Shared live-preview resolution and typography for timeline and clip preview.

Change ``DEFAULT_MAX_PREVIEW_LONG_SIDE`` here for the repo default. The API reads it
via ``pixfabrica_api.server_config`` (override with ``PIXFABRICA_MAX_PREVIEW_LONG_SIDE``).
The web client gets the live value from ``GET /config``; keep its bootstrap fallback in sync.
"""

from __future__ import annotations

from pixfabrica_core.theme.typography import FontPalette

DEFAULT_MAX_PREVIEW_LONG_SIDE = 480
# Back-compat alias for tests and callers that imported the old name.
MAX_PREVIEW_LONG_SIDE = DEFAULT_MAX_PREVIEW_LONG_SIDE
DEFAULT_REFERENCE_HEIGHT = 1080


def preview_dimensions(
    width: int,
    height: int,
    *,
    max_long_side: int = DEFAULT_MAX_PREVIEW_LONG_SIDE,
) -> tuple[int, int]:
    """Return (preview_w, preview_h) capped at ``max_long_side`` on the longest axis, min 1px."""
    cap = max(1, int(max_long_side))
    w = max(1, int(width))
    h = max(1, int(height))
    long_side = max(w, h)
    if long_side <= cap:
        return w, h
    scale = cap / long_side
    return max(1, int(w * scale)), max(1, int(h * scale))


def scale_typography_for_job_height(
    typography: FontPalette,
    *,
    job_height: int,
    reference_height: int = DEFAULT_REFERENCE_HEIGHT,
) -> FontPalette:
    """Match :meth:`RenderJob` post-validate typography scaling (``height / reference_height``)."""
    ref = max(1, int(reference_height))
    height = max(1, int(job_height))
    factor = height / ref
    if factor == 1.0:
        return typography
    return typography.scale(factor)
