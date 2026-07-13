"""Load gallery starters from portable bundles or legacy JSON."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from pixfabrica_api.gallery_media import rewrite_gallery_media_refs
from pixfabrica_api.gallery_scan import (
    resolve_gallery_bundle_path,
    resolve_gallery_project_path,
)
from pixfabrica_core.catalog import CatalogCache
from pixfabrica_core.project_bundles.errors import BundleImportError
from pixfabrica_core.project_bundles.import_bundle import import_project_bundle


def gallery_bundle_extract_dir(media_root: Path, category: str, slug: str) -> Path:
    return (media_root / "bundles" / "gallery" / category / slug).resolve()


def load_gallery_starter_project(
    gallery_root: Path,
    category: str,
    slug: str,
    *,
    media_root: Path,
    catalog: CatalogCache,
) -> dict[str, Any]:
    """Return a host-ready project document for the editor."""
    bundle_path = resolve_gallery_bundle_path(gallery_root, category, slug)
    if bundle_path.is_file():
        bundle_dir = gallery_bundle_extract_dir(media_root, category, slug)
        if bundle_dir.exists():
            shutil.rmtree(bundle_dir)
        try:
            return import_project_bundle(
                bundle_path.read_bytes(),
                bundle_dir=bundle_dir,
                catalog=catalog,
            )
        except BundleImportError as exc:
            raise ValueError(str(exc)) from exc

    json_path = resolve_gallery_project_path(gallery_root, category, slug)
    if not json_path.is_file():
        raise FileNotFoundError(f"starter not found: {category}/{slug}")

    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("invalid starter json") from exc
    if not isinstance(data, dict):
        raise ValueError("invalid starter json")
    return rewrite_gallery_media_refs(data, media_root)
