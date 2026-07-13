"""Font catalog, manifest, and bundled/extra directory resolution."""

from __future__ import annotations

from pathlib import Path

from pixfabrica_core.fonts.build import FontBuildResult, run_font_build
from pixfabrica_core.fonts.catalog import build_font_catalog, resolve_font_file
from pixfabrica_core.fonts.install import (
    FontInstallResult,
    install_font_sources,
    install_font_upload,
    install_fonts_from_directory,
)
from pixfabrica_core.fonts.manifest import FontManifestError, load_manifest
from pixfabrica_core.fonts.models import FontFamilyEntry, FontManifest, FontWeightEntry
from pixfabrica_core.fonts.paths import (
    MAX_FONT_UPLOAD_BYTES,
    default_bundled_fonts_dir,
    default_manifest_path,
    extra_fonts_dir,
    repo_root,
    user_fonts_dir,
)
from pixfabrica_core.fonts.skia_resolver import (
    clear_skia_font_cache,
    make_skia_font,
    resolve_font_source_path,
    resolve_skia_typeface,
    warmup_typography_palette,
)

_catalog_cache: list[FontFamilyEntry] | None = None


def get_font_catalog(*, reload: bool = False) -> list[FontFamilyEntry]:
    global _catalog_cache
    if reload or _catalog_cache is None:
        _catalog_cache = build_font_catalog()
    return list(_catalog_cache)


def rebuild_font_catalog() -> list[FontFamilyEntry]:
    return get_font_catalog(reload=True)


def configure_fonts_for_tests(
    *,
    bundled_dir: Path,
    extra_dir: Path | None = None,
    user_dir: Path | None = None,
) -> None:
    """Point default bundled/extra/user dirs at fixtures (tests only)."""
    import os

    os.environ["PIXFABRICA_BUNDLED_FONTS_DIR"] = str(bundled_dir.resolve())
    if extra_dir is None:
        os.environ.pop("PIXFABRICA_FONTS_DIR", None)
    else:
        os.environ["PIXFABRICA_FONTS_DIR"] = str(extra_dir.resolve())
    if user_dir is None:
        os.environ.pop("PIXFABRICA_USER_FONTS_DIR", None)
    else:
        os.environ["PIXFABRICA_USER_FONTS_DIR"] = str(user_dir.resolve())
    rebuild_font_catalog()
    clear_skia_font_cache()


__all__ = [
    "FontBuildResult",
    "FontFamilyEntry",
    "FontInstallResult",
    "FontManifest",
    "FontManifestError",
    "FontWeightEntry",
    "MAX_FONT_UPLOAD_BYTES",
    "build_font_catalog",
    "clear_skia_font_cache",
    "configure_fonts_for_tests",
    "default_bundled_fonts_dir",
    "default_manifest_path",
    "extra_fonts_dir",
    "get_font_catalog",
    "install_font_sources",
    "install_font_upload",
    "install_fonts_from_directory",
    "load_manifest",
    "make_skia_font",
    "rebuild_font_catalog",
    "repo_root",
    "resolve_font_file",
    "resolve_font_source_path",
    "resolve_skia_typeface",
    "run_font_build",
    "user_fonts_dir",
    "warmup_typography_palette",
]
