"""Media upload directory and public URL helpers."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import Request

_ENV_MEDIA_ROOT = "PIXFABRICA_MEDIA_ROOT"
_ENV_PUBLIC_API_URL = "PUBLIC_API_URL"
_DEFAULT_MEDIA_ROOT = Path("media")


def media_root() -> Path:
    raw = os.environ.get(_ENV_MEDIA_ROOT, "").strip()
    root = Path(raw) if raw else _DEFAULT_MEDIA_ROOT
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def public_base_url(request: Request) -> str:
    explicit = os.environ.get(_ENV_PUBLIC_API_URL, "").strip().rstrip("/")
    if explicit:
        return explicit
    return str(request.base_url).rstrip("/")
