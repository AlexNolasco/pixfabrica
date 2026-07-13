"""Content-addressed identity for local audio files (sidecar + lazy SHA-256)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

AUDIO_CONTENT_SIDECAR_SUFFIX = ".pixfabrica-audio.json"
_HASH_CHUNK = 1024 * 1024


def audio_content_sidecar_path(media_file: Path) -> Path:
    return media_file.parent / f"{media_file.name}{AUDIO_CONTENT_SIDECAR_SUFFIX}"


def write_audio_content_sidecar(
    media_file: Path,
    *,
    content_sha256: str,
    size: int,
) -> Path:
    """Persist hash from upload (bytes already in memory)."""
    path = audio_content_sidecar_path(media_file)
    payload = {"content_sha256": content_sha256, "size": size}
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _read_sidecar(media_file: Path) -> dict[str, Any] | None:
    path = audio_content_sidecar_path(media_file)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return raw if isinstance(raw, dict) else None


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(_HASH_CHUNK)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def content_sha256_for_path(path: Path) -> str:
    """Return SHA-256 of file bytes; reuse sidecar when size still matches."""
    st = path.stat()
    sidecar = _read_sidecar(path)
    if sidecar is not None:
        recorded = sidecar.get("content_sha256")
        recorded_size = sidecar.get("size")
        if isinstance(recorded, str) and len(recorded) == 64 and recorded_size == st.st_size:
            return recorded

    hexdigest = _hash_file(path)
    write_audio_content_sidecar(path, content_sha256=hexdigest, size=st.st_size)
    return hexdigest
