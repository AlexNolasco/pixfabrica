"""Upload-time image optimization for API media uploads (Pillow)."""

from __future__ import annotations

from pathlib import Path

from pixfabrica_core.image_optimize import (
    ImageOptimizeError,
    ImageOptimizeResult,
    optimize_image_file,
)

__all__ = ["ImageOptimizeError", "ImageOptimizeResult", "optimize_image_upload"]


def optimize_image_upload(source: Path, max_px: int) -> ImageOptimizeResult:
    """Apply a node file policy cap to an uploaded image."""
    return optimize_image_file(source, max_px)
