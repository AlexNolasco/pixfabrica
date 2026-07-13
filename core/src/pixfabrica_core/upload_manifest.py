"""Sidecar manifest written beside uploaded media when upload context is provided."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

UPLOAD_MANIFEST_SUFFIX = ".pixfabrica-upload.json"


def upload_manifest_path(media_file: Path) -> Path:
    return media_file.parent / f"{media_file.name}{UPLOAD_MANIFEST_SUFFIX}"


def write_upload_manifest(
    media_file: Path,
    *,
    clip_type: str,
    plugin_id: str,
    kind: str,
    size: int,
    content_sha256: str,
    optimized_for: dict[str, int | float] | None = None,
) -> Path:
    """Write or replace the upload context manifest next to ``media_file``."""
    payload: dict[str, Any] = {
        "clip_type": clip_type,
        "plugin_id": plugin_id,
        "kind": kind,
        "size": size,
        "content_sha256": content_sha256,
        "uploaded_at": datetime.now(UTC).isoformat(),
    }
    if optimized_for is not None:
        payload["optimized_for"] = optimized_for
    path = upload_manifest_path(media_file)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def read_upload_manifest(media_file: Path) -> dict[str, Any] | None:
    """Return parsed upload manifest for *media_file*, or ``None`` if missing."""
    path = upload_manifest_path(media_file)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
