"""Shared media upload limits and helpers for API + gen-ui."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from pixfabrica_core.clips import ClipCategory

MediaUploadKind = Literal["audio", "image", "lyrics", "video", "mesh", "default"]

_LOSSLESS_AUDIO_EXT = frozenset({".wav", ".flac"})

# see also FALLBACK_UPLOAD_LIMITS  on the web
MEDIA_UPLOAD_LIMITS: dict[str, int] = {
    "audio": 10 * 1024 * 1024,
    "audio_lossless": 60 * 1024 * 1024,
    "image": 10 * 1024 * 1024,
    "lyrics": 5 * 1024 * 1024,
    "video": 15 * 1024 * 1024,
    "mesh": 10 * 1024 * 1024,
    "default": 16 * 1024 * 1024,
}

MEDIA_ACCEPT: dict[MediaUploadKind, list[str]] = {
    "audio": [".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac"],
    "image": [".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"],
    "lyrics": [".lrc", ".srt", ".vtt", ".json"],
    "video": [".mp4", ".mov", ".webm", ".mkv"],
    "mesh": [".gltf", ".glb"],
    "default": [],
}

_CATEGORY_TO_KIND: dict[str, MediaUploadKind] = {
    ClipCategory.AUDIO.value: "audio",
    ClipCategory.IMAGE.value: "image",
    ClipCategory.LYRICS.value: "lyrics",
    ClipCategory.TEXT.value: "lyrics",
    ClipCategory.VIDEO.value: "video",
    ClipCategory.MESH.value: "mesh",
    ClipCategory.BACKGROUND.value: "image",
}

_EXTENSION_TO_KIND: dict[str, MediaUploadKind] = {}
for _kind, _exts in MEDIA_ACCEPT.items():
    for _ext in _exts:
        _EXTENSION_TO_KIND[_ext.lower()] = _kind

_SAFE_BASENAME = re.compile(r"^[A-Za-z0-9._ -]+$")


def kind_for_clip_category(category: object) -> MediaUploadKind:
    key = category.value if isinstance(category, ClipCategory) else str(category or "")
    return _CATEGORY_TO_KIND.get(key, "default")


def max_bytes_for_kind(kind: str) -> int:
    if kind in MEDIA_UPLOAD_LIMITS:
        return MEDIA_UPLOAD_LIMITS[kind]
    return MEDIA_UPLOAD_LIMITS["default"]


def is_lossless_audio_filename(filename: str) -> bool:
    return Path(filename).suffix.lower() in _LOSSLESS_AUDIO_EXT


def max_bytes_for_audio_upload(filename: str) -> int:
    if is_lossless_audio_filename(filename):
        return MEDIA_UPLOAD_LIMITS["audio_lossless"]
    return MEDIA_UPLOAD_LIMITS["audio"]


def accept_for_kind(kind: str) -> list[str]:
    k: MediaUploadKind = kind if kind in MEDIA_ACCEPT else "default"
    return list(MEDIA_ACCEPT[k])


def kind_for_extension(filename: str) -> MediaUploadKind:
    ext = Path(filename).suffix.lower()
    return _EXTENSION_TO_KIND.get(ext, "default")


def sanitize_upload_basename(filename: str) -> str:
    """Return a safe basename for storage under MEDIA_ROOT."""
    raw = Path(filename).name.strip()
    if not raw or raw in {".", ".."}:
        raise ValueError("invalid filename")
    base = Path(raw).name
    if not _SAFE_BASENAME.match(base):
        raise ValueError("filename contains unsupported characters")
    return base


def resolve_media_path(media_root: Path, filename: str) -> Path:
    """Resolve path under media_root; raise if it escapes the root."""
    root = media_root.resolve()
    dest = (root / filename).resolve()
    if not dest.is_relative_to(root):
        raise ValueError("invalid path")
    return dest
