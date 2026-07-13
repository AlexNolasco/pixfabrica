"""Pexels stock media integration — API key and ingest limits."""

from __future__ import annotations

import os

_DEFAULT_PER_PAGE = 15
_MAX_PER_PAGE = 80

PEXELS_DEFAULT_PER_PAGE = _DEFAULT_PER_PAGE
PEXELS_MAX_PER_PAGE = _MAX_PER_PAGE

_DEFAULT_QUERIES: tuple[str, ...] = ("inspirational", "music")
_DEFAULT_VIDEO_QUERIES: tuple[str, ...] = ("cinematic", "abstract", "motion")
_MAX_DEFAULT_QUERIES = 8
_MAX_QUERY_LEN = 200


def pexels_api_key() -> str | None:
    raw = os.environ.get("PIXFABRICA_PEXELS_API_KEY", "").strip()
    return raw or None


def pexels_available() -> bool:
    return pexels_api_key() is not None


def pexels_default_per_page() -> int:
    return PEXELS_DEFAULT_PER_PAGE


def pexels_max_per_page() -> int:
    return PEXELS_MAX_PER_PAGE


def pexels_default_queries() -> tuple[str, ...]:
    """Quick-pick search tags for the stock photos panel."""
    raw = os.environ.get("PIXFABRICA_PEXELS_DEFAULT_QUERIES", "").strip()
    if not raw:
        return _DEFAULT_QUERIES

    queries: list[str] = []
    for part in raw.split(","):
        query = part.strip()
        if not query or len(query) > _MAX_QUERY_LEN:
            continue
        if query in queries:
            continue
        queries.append(query)
        if len(queries) >= _MAX_DEFAULT_QUERIES:
            break
    return tuple(queries) if queries else _DEFAULT_QUERIES


def pexels_default_video_queries() -> tuple[str, ...]:
    """Quick-pick search tags for the stock videos panel."""
    raw = os.environ.get("PIXFABRICA_PEXELS_DEFAULT_VIDEO_QUERIES", "").strip()
    if not raw:
        return _DEFAULT_VIDEO_QUERIES

    queries: list[str] = []
    for part in raw.split(","):
        query = part.strip()
        if not query or len(query) > _MAX_QUERY_LEN:
            continue
        if query in queries:
            continue
        queries.append(query)
        if len(queries) >= _MAX_DEFAULT_QUERIES:
            break
    return tuple(queries) if queries else _DEFAULT_VIDEO_QUERIES
