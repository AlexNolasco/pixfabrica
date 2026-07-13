"""Shared raster image downsample — used by API upload and clip prepare safety nets."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image as PILImage

from pixfabrica_core.file_upload_policy import ImageOptimizedFor


class ImageOptimizeError(Exception):
    """Raised when an image cannot be decoded or written."""


@dataclass(frozen=True, slots=True)
class ImageOptimizeResult:
    path: Path
    optimized_for: ImageOptimizedFor
    resized: bool


def downsample_pil_image(pil_img: PILImage.Image, max_px: int) -> tuple[PILImage.Image, bool]:
    """Return RGBA image scaled to fit within ``max_px`` on the long edge (aspect preserved)."""
    rgba = pil_img.convert("RGBA")
    width, height = rgba.size
    if max(width, height) <= max_px:
        return rgba, False
    resized = rgba.copy()
    resized.thumbnail((max_px, max_px), PILImage.Resampling.LANCZOS)
    return resized, True


def optimize_image_file(source: Path, max_px: int) -> ImageOptimizeResult:
    """Downsample ``source`` in place when it exceeds ``max_px``; preserve aspect ratio."""
    try:
        with PILImage.open(source) as opened:
            rgba, resized = downsample_pil_image(opened, max_px)
    except OSError as exc:
        raise ImageOptimizeError(f"failed to decode image: {exc}") from exc

    width, height = rgba.size
    if resized:
        _save_rgba(source, rgba)

    return ImageOptimizeResult(
        path=source,
        optimized_for=ImageOptimizedFor(width=width, height=height),
        resized=resized,
    )


def _save_rgba(path: Path, rgba: PILImage.Image) -> None:
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        rgba.convert("RGB").save(path, format="JPEG", quality=90, optimize=True)
        return
    if suffix == ".webp":
        rgba.save(path, format="WEBP", quality=90, method=6)
        return
    if suffix == ".gif":
        rgba.save(path, format="PNG", optimize=True)
        return
    rgba.save(path, format="PNG", optimize=True)
