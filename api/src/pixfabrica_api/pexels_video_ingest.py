"""Select and ingest Pexels video file URLs into local media storage."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pixfabrica_api.media_fetch import MediaFetchError, fetch_url_to_path
from pixfabrica_api.pexels_ingest import is_pexels_media_url
from pixfabrica_core.media_upload import max_bytes_for_kind, sanitize_upload_basename

_PEXELS_VIDEO_HOST_SUFFIXES = ("player.vimeo.com",)


class PexelsVideoIngestError(Exception):
    """Raised when no Pexels video file could be ingested."""


def is_pexels_video_file_url(url: str) -> bool:
    """True for Pexels-hosted media and Vimeo CDN links returned by the Pexels API."""
    if is_pexels_media_url(url):
        return True
    trimmed = url.strip()
    if not trimmed.startswith(("http://", "https://")):
        return False
    try:
        host = (urlparse(trimmed).hostname or "").lower()
    except ValueError:
        return False
    return host in _PEXELS_VIDEO_HOST_SUFFIXES


def _normalized_video_files(
    video_files: Sequence[Mapping[str, Any]],
) -> list[dict[str, int | str]]:
    normalized: list[dict[str, int | str]] = []
    for entry in video_files:
        if not isinstance(entry, Mapping):
            continue
        link = entry.get("link")
        if not isinstance(link, str) or not is_pexels_video_file_url(link):
            continue
        width_raw = entry.get("width")
        height_raw = entry.get("height")
        if width_raw is None or height_raw is None:
            continue
        try:
            width = int(width_raw)
            height = int(height_raw)
        except (TypeError, ValueError):
            continue
        if width <= 0 or height <= 0:
            continue
        size_raw = entry.get("size")
        try:
            file_size = int(size_raw) if size_raw is not None else width * height
        except (TypeError, ValueError):
            file_size = width * height
        normalized.append(
            {
                "link": link,
                "width": width,
                "height": height,
                "size": max(1, file_size),
            }
        )
    return normalized


def select_pexels_video_file(
    video_files: Sequence[Mapping[str, Any]],
    *,
    target_width: int,
    target_height: int,
) -> dict[str, int | str] | None:
    """Pick the largest file at or below job size, else the smallest file above."""
    candidates = _normalized_video_files(video_files)
    if not candidates:
        return None

    under = [
        c
        for c in candidates
        if int(c["width"]) <= target_width and int(c["height"]) <= target_height
    ]
    if under:
        return max(
            under,
            key=lambda c: (
                int(c["width"]) * int(c["height"]),
                int(c["width"]),
                int(c["height"]),
            ),
        )

    over = [
        c for c in candidates if int(c["width"]) > target_width or int(c["height"]) > target_height
    ]
    if not over:
        return None
    return min(
        over,
        key=lambda c: (
            int(c["width"]) * int(c["height"]),
            int(c["size"]),
        ),
    )


def _video_extension_from_url(url: str) -> str:
    path = urlparse(url).path
    ext = Path(path).suffix.lower()
    if ext in {".mp4", ".mov", ".webm"}:
        return ext
    return ".mp4"


def allocate_video_ingest_path(media_root: Path, url: str) -> Path:
    digest = hashlib.sha256(url.strip().encode()).hexdigest()[:20]
    ext = _video_extension_from_url(url)
    name = sanitize_upload_basename(f"ingest-{digest}{ext}")
    return media_root / name


def ingest_pexels_video(
    video_files: Sequence[Mapping[str, Any]],
    *,
    target_width: int,
    target_height: int,
    media_root: Path,
) -> Path:
    selected = select_pexels_video_file(
        video_files,
        target_width=target_width,
        target_height=target_height,
    )
    if selected is None:
        raise PexelsVideoIngestError("no ingestible pexels video file")

    url = str(selected["link"])
    max_bytes = max_bytes_for_kind("video")
    dest = allocate_video_ingest_path(media_root, url)
    if dest.is_file():
        return dest

    try:
        fetch_url_to_path(url, dest, max_bytes=max_bytes)
    except MediaFetchError as exc:
        dest.unlink(missing_ok=True)
        raise PexelsVideoIngestError(str(exc)) from exc

    return dest
