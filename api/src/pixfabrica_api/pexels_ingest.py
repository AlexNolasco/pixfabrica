"""Select and ingest Pexels photo URLs into local media storage."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlparse

from pixfabrica_api.media_fetch import MediaFetchError, allocate_ingest_path, fetch_url_to_path
from pixfabrica_core.media_upload import max_bytes_for_kind

_PEXELS_HOST_SUFFIXES = (".pexels.com",)


class PexelsIngestError(Exception):
    """Raised when no Pexels URL could be ingested."""


def is_pexels_media_url(url: str) -> bool:
    trimmed = url.strip()
    if not trimmed.startswith(("http://", "https://")):
        return False
    try:
        host = urlparse(trimmed).hostname or ""
    except ValueError:
        return False
    host = host.lower()
    return any(host == suffix[1:] or host.endswith(suffix) for suffix in _PEXELS_HOST_SUFFIXES)


def pexels_ingest_url_candidates(src: Mapping[str, str | None], orientation: str) -> list[str]:
    """Orientation-aware URL first, then large; original last (S2)."""
    candidates: list[str] = []

    def add(url: str | None) -> None:
        if url and url not in candidates:
            candidates.append(url)

    if orientation == "portrait":
        add(src.get("portrait"))
    elif orientation == "landscape":
        add(src.get("landscape"))
    else:
        add(src.get("large"))

    add(src.get("large"))
    add(src.get("original"))
    return candidates


def ingest_pexels_photo(
    src: Mapping[str, str | None],
    *,
    orientation: str,
    media_root: Path,
) -> Path:
    max_bytes = max_bytes_for_kind("image")
    original_url = src.get("original")
    last_error: Exception | None = None

    for url in pexels_ingest_url_candidates(src, orientation):
        if not is_pexels_media_url(url):
            continue
        if url == original_url:
            # Original is last-resort only when smaller candidates failed.
            pass
        dest = allocate_ingest_path(media_root, url)
        if dest.is_file():
            return dest
        try:
            fetch_url_to_path(url, dest, max_bytes=max_bytes)
            return dest
        except MediaFetchError as exc:
            last_error = exc
            dest.unlink(missing_ok=True)
            continue

    message = str(last_error) if last_error else "no ingestible pexels url"
    raise PexelsIngestError(message)
