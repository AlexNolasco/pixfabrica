"""Starter gallery directory on the API host."""

from __future__ import annotations

import os
from pathlib import Path

_ENV_GALLERY_ROOT = "PIXFABRICA_GALLERY_ROOT"
_DEFAULT_GALLERY_ROOT = Path(__file__).resolve().parents[2] / "media" / "gallery"


def gallery_root() -> Path:
    raw = os.environ.get(_ENV_GALLERY_ROOT, "").strip()
    root = Path(raw) if raw else _DEFAULT_GALLERY_ROOT
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


_ENV_GALLERY_PUBLISH = "PIXFABRICA_GALLERY_PUBLISH"


def gallery_publish_enabled() -> bool:
    """When false, ``POST /gallery/publish`` returns 403 (disable in production)."""
    raw = os.environ.get(_ENV_GALLERY_PUBLISH, "1").strip().lower()
    return raw in {"1", "true", "yes", "on"}
