"""Repository font directory resolution."""

from __future__ import annotations

import os
from pathlib import Path

_ENV_FONTS_DIR = "PIXFABRICA_FONTS_DIR"
_ENV_USER_FONTS_DIR = "PIXFABRICA_USER_FONTS_DIR"
_ENV_REPO_ROOT = "PIXFABRICA_REPO_ROOT"
_ENV_BUNDLED_FONTS_DIR = "PIXFABRICA_BUNDLED_FONTS_DIR"
_DEFAULT_USER_FONTS_ROOT = Path("user-fonts")
MAX_FONT_UPLOAD_BYTES = 32 * 1024 * 1024
_MAX_FONT_BYTES = MAX_FONT_UPLOAD_BYTES
_ALLOWED_SUFFIXES = frozenset({".ttf", ".otf", ".woff", ".woff2"})
_FONT_SOURCE_SUFFIXES = frozenset({".ttf", ".otf"})


def repo_root() -> Path:
    explicit = os.environ.get(_ENV_REPO_ROOT, "").strip()
    if explicit:
        return Path(explicit).resolve()
    # core/src/pixfabrica_core/fonts/paths.py → repo root is parents[4]
    return Path(__file__).resolve().parents[4]


def default_bundled_fonts_dir() -> Path:
    override = os.environ.get(_ENV_BUNDLED_FONTS_DIR, "").strip()
    if override:
        return Path(override).resolve()
    return (repo_root() / "assets" / "fonts").resolve()


def user_fonts_dir() -> Path:
    """Web-uploaded and bundle-imported fonts (always scanned)."""
    raw = os.environ.get(_ENV_USER_FONTS_DIR, "").strip()
    root = Path(raw) if raw else _DEFAULT_USER_FONTS_ROOT
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def extra_fonts_dir() -> Path | None:
    raw = os.environ.get(_ENV_FONTS_DIR, "").strip()
    if not raw:
        return None
    return Path(raw).resolve()


def default_manifest_path(fonts_dir: Path | None = None) -> Path:
    root = fonts_dir if fonts_dir is not None else default_bundled_fonts_dir()
    return root / "manifest.json"


def is_allowed_font_path(path: Path) -> bool:
    if path.suffix.lower() not in _ALLOWED_SUFFIXES:
        return False
    if path.is_symlink():
        return False
    try:
        size = path.stat().st_size
    except OSError:
        return False
    return 0 < size <= _MAX_FONT_BYTES


def woff2_path_for_source(source: str) -> str:
    path = Path(source)
    return str(path.with_suffix(".woff2"))
