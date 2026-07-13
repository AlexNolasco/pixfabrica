"""Hosted API policy limits — env-configurable, not enforced in core/renderer."""

from __future__ import annotations

import logging
import os

from pixfabrica_core.media_upload import MEDIA_UPLOAD_LIMITS
from pixfabrica_core.preview_dims import DEFAULT_MAX_PREVIEW_LONG_SIDE

logger = logging.getLogger(__name__)

SUPPORTED_LOCALES: frozenset[str] = frozenset({"en", "es", "zh-CN", "ja"})
FALLBACK_LOCALE = "en"

DEFAULT_MAX_TRACKS = 16
DEFAULT_MAX_CLIPS_PER_TRACK = 8
DEFAULT_MAX_DURATION_S = 600
DEFAULT_MAX_WIDTH = 1920
DEFAULT_MAX_HEIGHT = 1080
DEFAULT_MAX_FPS = 30


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return max(1, int(raw))


MAX_PREVIEW_LONG_SIDE = _int_env(
    "PIXFABRICA_MAX_PREVIEW_LONG_SIDE",
    DEFAULT_MAX_PREVIEW_LONG_SIDE,
)
MAX_TRACKS = _int_env("PIXFABRICA_MAX_TRACKS", DEFAULT_MAX_TRACKS)
MAX_CLIPS_PER_TRACK = _int_env(
    "PIXFABRICA_MAX_CLIPS_PER_TRACK",
    DEFAULT_MAX_CLIPS_PER_TRACK,
)
MAX_DURATION_S = _int_env("PIXFABRICA_MAX_DURATION_S", DEFAULT_MAX_DURATION_S)
MAX_WIDTH = _int_env("PIXFABRICA_MAX_WIDTH", DEFAULT_MAX_WIDTH)
MAX_HEIGHT = _int_env("PIXFABRICA_MAX_HEIGHT", DEFAULT_MAX_HEIGHT)
MAX_FPS = _int_env("PIXFABRICA_MAX_FPS", DEFAULT_MAX_FPS)


def resolve_default_locale(raw: str | None) -> str:
    """Validate ``PIXFABRICA_DEFAULT_LOCALE``; clamp invalid values to ``en``."""
    if raw is None or raw.strip() == "":
        return FALLBACK_LOCALE
    tag = raw.strip()
    if tag in SUPPORTED_LOCALES:
        return tag
    logger.warning(
        "PIXFABRICA_DEFAULT_LOCALE=%r is not supported (%s); using %r",
        raw,
        ", ".join(sorted(SUPPORTED_LOCALES)),
        FALLBACK_LOCALE,
    )
    return FALLBACK_LOCALE


DEFAULT_LOCALE = resolve_default_locale(os.environ.get("PIXFABRICA_DEFAULT_LOCALE"))


def upload_limits_payload() -> dict[str, int]:
    limits: dict[str, int] = {}
    for kind, nbytes in MEDIA_UPLOAD_LIMITS.items():
        limits[kind] = nbytes
    return limits
