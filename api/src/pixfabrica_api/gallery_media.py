"""Resolve portable media/… references in gallery starter JSON on this API host."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pixfabrica_core.media_upload import resolve_media_path

_PORTABLE_MEDIA_REF = re.compile(r"^/?media/(.+)$", re.IGNORECASE)


def is_portable_media_ref(value: str) -> bool:
    return bool(_PORTABLE_MEDIA_REF.match(value.strip()))


def resolve_portable_media_ref(value: str, media_root: Path) -> str:
    """Rewrite ``media/foo.jpg`` or ``/media/foo.jpg`` to an absolute path under *media_root*."""
    raw = value.strip()
    match = _PORTABLE_MEDIA_REF.match(raw)
    if not match:
        return value
    rel = match.group(1).replace("\\", "/")
    try:
        return str(resolve_media_path(media_root.resolve(), rel).resolve())
    except ValueError:
        return value


def rewrite_gallery_media_refs(project: Any, media_root: Path) -> Any:
    """Deep-walk a gallery starter and resolve portable ``media/…`` string refs in place."""
    if isinstance(project, dict):
        return {key: rewrite_gallery_media_refs(val, media_root) for key, val in project.items()}
    if isinstance(project, list):
        return [rewrite_gallery_media_refs(item, media_root) for item in project]
    if isinstance(project, str):
        return resolve_portable_media_ref(project, media_root)
    return project
