"""Fetch remote media URLs into local storage for web/API ingest."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from urllib.parse import urlparse

import httpx

from pixfabrica_core.media_upload import sanitize_upload_basename

log = logging.getLogger("pixfabrica.api.media_fetch")


class MediaFetchError(Exception):
    """Raised when a remote URL cannot be fetched."""


def _extension_from_url(url: str) -> str:
    path = urlparse(url).path
    ext = Path(path).suffix.lower()
    if ext in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}:
        return ext
    return ".img"


def ingest_filename_for_url(url: str) -> str:
    """Stable media basename for a remote URL (dedup re-ingest of the same URL)."""
    digest = hashlib.sha256(url.strip().encode()).hexdigest()[:20]
    return f"ingest-{digest}{_extension_from_url(url)}"


def fetch_url_to_path(url: str, dest: Path, *, max_bytes: int) -> None:
    """Download ``url`` to ``dest`` when under ``max_bytes``."""
    trimmed = url.strip()
    if not trimmed.startswith(("http://", "https://")):
        raise MediaFetchError("URL must start with http:// or https://")

    try:
        with (
            httpx.Client(follow_redirects=True, timeout=60.0) as client,
            client.stream("GET", trimmed) as response,
        ):
            response.raise_for_status()
            content_length = response.headers.get("content-length")
            if content_length is not None:
                try:
                    if int(content_length) > max_bytes:
                        raise MediaFetchError(
                            f"remote file exceeds {max_bytes} byte limit for kind"
                        )
                except ValueError:
                    pass

            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_suffix(dest.suffix + ".tmp")
            size = 0
            try:
                with tmp.open("wb") as handle:
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > max_bytes:
                            raise MediaFetchError(
                                f"remote file exceeds {max_bytes} byte limit for kind"
                            )
                        handle.write(chunk)
                tmp.replace(dest)
            except Exception:
                tmp.unlink(missing_ok=True)
                raise
    except httpx.HTTPError as exc:
        raise MediaFetchError(str(exc)) from exc


def allocate_ingest_path(root: Path, url: str) -> Path:
    """Return a safe destination path under ``root`` for ``url``."""
    name = sanitize_upload_basename(ingest_filename_for_url(url))
    return root / name
