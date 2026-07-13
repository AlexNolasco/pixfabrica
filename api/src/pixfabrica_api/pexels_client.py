"""Pexels HTTP client for server-side search proxy."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

import httpx

from pixfabrica_api.pexels_settings import pexels_api_key

_PEXELS_PHOTOS_BASE = "https://api.pexels.com/v1"
_PEXELS_VIDEOS_BASE = "https://api.pexels.com/videos"
_VALID_ORIENTATIONS = frozenset({"landscape", "portrait", "square"})
_VALID_SIZES = frozenset({"large", "medium", "small"})


class PexelsClientError(Exception):
    """Raised when the Pexels API returns an error or is unreachable."""

    def __init__(self, message: str, *, retry_after_s: int | None = None) -> None:
        super().__init__(message)
        self.retry_after_s = retry_after_s


def _parse_retry_after(raw: str | None) -> int | None:
    if not raw:
        return None
    try:
        return max(1, min(int(raw.strip()), 3600))
    except ValueError:
        return None


def normalize_orientation(width: int, height: int) -> str:
    if width == height:
        return "square"
    if height > width:
        return "portrait"
    return "landscape"


def _parse_photos(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = payload.get("photos")
    if not isinstance(raw, list):
        return []
    photos: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        src = entry.get("src")
        if not isinstance(src, dict):
            continue
        photos.append(
            {
                "id": entry.get("id"),
                "width": entry.get("width"),
                "height": entry.get("height"),
                "alt": entry.get("alt"),
                "photographer": entry.get("photographer"),
                "photographer_url": entry.get("photographer_url"),
                "url": entry.get("url"),
                "src": {
                    "tiny": src.get("tiny"),
                    "small": src.get("small"),
                    "medium": src.get("medium"),
                    "large": src.get("large"),
                    "large2x": src.get("large2x"),
                    "portrait": src.get("portrait"),
                    "landscape": src.get("landscape"),
                    "original": src.get("original"),
                },
            }
        )
    return photos


async def search_pexels_photos(
    *,
    query: str,
    orientation: str,
    page: int,
    per_page: int,
    size: str = "medium",
) -> dict[str, Any]:
    key = pexels_api_key()
    if not key:
        raise PexelsClientError("pexels_not_configured")

    trimmed = query.strip()
    if not trimmed:
        raise PexelsClientError("query is required")

    if orientation not in _VALID_ORIENTATIONS:
        raise PexelsClientError(f"invalid orientation: {orientation}")

    if size not in _VALID_SIZES:
        raise PexelsClientError(f"invalid size: {size}")

    params = urlencode(
        {
            "query": trimmed,
            "orientation": orientation,
            "size": size,
            "page": max(1, page),
            "per_page": per_page,
        }
    )
    url = f"{_PEXELS_PHOTOS_BASE}/search?{params}"
    headers = {"Authorization": key}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        raise PexelsClientError(str(exc)) from exc

    if response.status_code == 401:
        raise PexelsClientError("pexels_unauthorized")
    if response.status_code == 429:
        raise PexelsClientError(
            "pexels_rate_limited",
            retry_after_s=_parse_retry_after(response.headers.get("Retry-After")),
        )
    if response.status_code >= 400:
        raise PexelsClientError(f"pexels_http_{response.status_code}")

    try:
        payload = response.json()
    except ValueError as exc:
        raise PexelsClientError("invalid_pexels_response") from exc

    if not isinstance(payload, dict):
        raise PexelsClientError("invalid_pexels_response")

    return {
        "page": payload.get("page", page),
        "per_page": payload.get("per_page", per_page),
        "total_results": payload.get("total_results", 0),
        "next_page": payload.get("next_page"),
        "photos": _parse_photos(payload),
    }


def _parse_video_files(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    files: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        link = entry.get("link")
        width = entry.get("width")
        height = entry.get("height")
        if not isinstance(link, str) or not link.strip():
            continue
        if width is None or height is None:
            continue
        try:
            w = int(width)
            h = int(height)
        except (TypeError, ValueError):
            continue
        if w <= 0 or h <= 0:
            continue
        file_id = entry.get("id")
        fps = entry.get("fps")
        size = entry.get("size")
        files.append(
            {
                "id": file_id,
                "quality": entry.get("quality"),
                "file_type": entry.get("file_type"),
                "width": w,
                "height": h,
                "fps": fps,
                "size": size,
                "link": link,
            }
        )
    return files


def _parse_videos(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = payload.get("videos")
    if not isinstance(raw, list):
        return []
    videos: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        user = entry.get("user")
        if not isinstance(user, dict):
            continue
        name = user.get("name")
        user_url = user.get("url")
        if not isinstance(name, str) or not isinstance(user_url, str):
            continue
        video_files = _parse_video_files(entry.get("video_files"))
        if not video_files:
            continue
        image = entry.get("image")
        page_url = entry.get("url")
        if not isinstance(image, str) or not isinstance(page_url, str):
            continue
        try:
            duration = int(entry.get("duration") or 0)
        except (TypeError, ValueError):
            duration = 0
        videos.append(
            {
                "id": entry.get("id"),
                "width": entry.get("width"),
                "height": entry.get("height"),
                "duration": max(0, duration),
                "url": page_url,
                "image": image,
                "user": {
                    "id": user.get("id"),
                    "name": name,
                    "url": user_url,
                },
                "video_files": video_files,
            }
        )
    return videos


async def search_pexels_videos(
    *,
    query: str,
    orientation: str,
    page: int,
    per_page: int,
) -> dict[str, Any]:
    key = pexels_api_key()
    if not key:
        raise PexelsClientError("pexels_not_configured")

    trimmed = query.strip()
    if not trimmed:
        raise PexelsClientError("query is required")

    if orientation not in _VALID_ORIENTATIONS:
        raise PexelsClientError(f"invalid orientation: {orientation}")

    params = urlencode(
        {
            "query": trimmed,
            "orientation": orientation,
            "page": max(1, page),
            "per_page": per_page,
        }
    )
    url = f"{_PEXELS_VIDEOS_BASE}/search?{params}"
    headers = {"Authorization": key}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        raise PexelsClientError(str(exc)) from exc

    if response.status_code == 401:
        raise PexelsClientError("pexels_unauthorized")
    if response.status_code == 429:
        raise PexelsClientError(
            "pexels_rate_limited",
            retry_after_s=_parse_retry_after(response.headers.get("Retry-After")),
        )
    if response.status_code >= 400:
        raise PexelsClientError(f"pexels_http_{response.status_code}")

    try:
        payload = response.json()
    except ValueError as exc:
        raise PexelsClientError("invalid_pexels_response") from exc

    if not isinstance(payload, dict):
        raise PexelsClientError("invalid_pexels_response")

    return {
        "page": payload.get("page", page),
        "per_page": payload.get("per_page", per_page),
        "total_results": payload.get("total_results", 0),
        "next_page": payload.get("next_page"),
        "videos": _parse_videos(payload),
    }
