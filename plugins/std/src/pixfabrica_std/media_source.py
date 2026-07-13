"""Media source path helpers for std plugins."""

from __future__ import annotations

import hashlib
from pathlib import Path

from pixfabrica_core.clips import PrepareContext


def resolve_local_source_path(source: str) -> Path:
    """Return a local filesystem path; remote URLs must be ingested before render."""
    trimmed = source.strip()
    if trimmed.startswith(("http://", "https://")):
        raise ValueError(f"remote source must be ingested to local media: {source!r}")
    return Path(trimmed)


def resolve_source_sync(source: str, ctx: PrepareContext) -> Path:
    """Resolve a local path or fetch http(s) into the job cache (legacy clip helpers)."""
    import httpx

    trimmed = source.strip()
    if trimmed.startswith(("http://", "https://")):
        cache_dir = ctx.cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)
        url_hash = hashlib.sha256(trimmed.encode()).hexdigest()
        ext = Path(trimmed.split("?")[0]).suffix or ".img"
        cached = cache_dir / f"{url_hash}{ext}"
        if not cached.exists():
            tmp = cache_dir / f"{url_hash}.tmp"
            with httpx.Client() as client:
                response = client.get(trimmed)
                response.raise_for_status()
                tmp.write_bytes(response.content)
            tmp.replace(cached)
        return cached

    return Path(trimmed)
