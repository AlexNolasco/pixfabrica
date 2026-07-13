"""Publish editor exports into the starter gallery folder layout."""

from __future__ import annotations

import copy
import json
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pixfabrica_api.gallery_scan import _valid_slug, gallery_bundle_filename
from pixfabrica_core.catalog import CatalogCache
from pixfabrica_core.project_bundles.errors import BundleExportError
from pixfabrica_core.project_bundles.export import export_project_bundle
from pixfabrica_core.project_bundles.format import (
    BUNDLE_MANIFEST_NAME,
    HOST_LOCAL_FIELDS,
    PROJECT_JSON_NAME,
    validate_bundle_manifest,
)


class GalleryPublishError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class GalleryPublishResult:
    gallery_json: Path
    thumbnail: Path
    gallery_bundle: Path | None
    media_refs: tuple[str, ...]


def _strip_host_local_fields(project: dict[str, Any]) -> None:
    for key in HOST_LOCAL_FIELDS:
        project.pop(key, None)


def _gallery_title_description(project: dict[str, Any]) -> tuple[str, str]:
    title_raw = project.get("title")
    title = str(title_raw).strip() if title_raw is not None else ""
    description_raw = project.get("description")
    description = str(description_raw).strip() if description_raw is not None else ""
    return title, description


def _write_gallery_metadata(path: Path, *, title: str, description: str) -> None:
    path.write_text(
        json.dumps({"title": title, "description": description}, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_gallery_starter_files(
    *,
    category: str,
    slug: str,
    thumb_src: Path,
    gallery_root: Path,
    bundle_src: Path | None,
    title: str,
    description: str,
) -> GalleryPublishResult:
    if not _valid_slug(category) or not _valid_slug(slug):
        raise GalleryPublishError("category and slug must match [A-Za-z0-9_-]+")

    category_dir = gallery_root / category
    category_dir.mkdir(parents=True, exist_ok=True)

    gallery_json = category_dir / f"{slug}.json"
    thumb_dest = category_dir / f"{slug}{thumb_src.suffix.lower()}"
    bundle_dest: Path | None = None

    _write_gallery_metadata(gallery_json, title=title, description=description)
    shutil.copy2(thumb_src, thumb_dest)

    if bundle_src is not None:
        bundle_dest = category_dir / gallery_bundle_filename(slug)
        shutil.copy2(bundle_src, bundle_dest)

    return GalleryPublishResult(
        gallery_json=gallery_json.resolve(),
        thumbnail=thumb_dest.resolve(),
        gallery_bundle=bundle_dest.resolve() if bundle_dest is not None else None,
        media_refs=(),
    )


def publish_json_to_gallery(
    project: dict[str, Any],
    *,
    category: str,
    slug: str,
    thumb_src: Path,
    gallery_root: Path,
    media_root: Path,
    catalog: CatalogCache,
) -> GalleryPublishResult:
    if not isinstance(project, dict):
        raise GalleryPublishError("project must be a JSON object")

    work = copy.deepcopy(project)
    _strip_host_local_fields(work)
    title, description = _gallery_title_description(work)

    try:
        bundle_bytes, _ = export_project_bundle(
            work,
            media_root=media_root,
            catalog=catalog,
        )
    except BundleExportError as exc:
        raise GalleryPublishError(str(exc)) from exc

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pixfabrica.zip") as tmp:
        tmp.write(bundle_bytes)
        tmp_path = Path(tmp.name)

    try:
        return publish_bundle_to_gallery(
            tmp_path,
            category=category,
            slug=slug,
            thumb_src=thumb_src,
            gallery_root=gallery_root,
            title=title,
            description=description,
        )
    finally:
        tmp_path.unlink(missing_ok=True)


def publish_bundle_to_gallery(
    bundle_path: Path,
    *,
    category: str,
    slug: str,
    thumb_src: Path,
    gallery_root: Path,
    title: str | None = None,
    description: str | None = None,
) -> GalleryPublishResult:
    try:
        with zipfile.ZipFile(bundle_path) as archive:
            try:
                manifest_raw = json.loads(archive.read(BUNDLE_MANIFEST_NAME))
            except KeyError as exc:
                raise GalleryPublishError("bundle missing bundle.json") from exc
            try:
                validate_bundle_manifest(manifest_raw)
            except ValueError as exc:
                raise GalleryPublishError(str(exc)) from exc

            try:
                project = json.loads(archive.read(PROJECT_JSON_NAME))
            except KeyError as exc:
                raise GalleryPublishError("bundle missing project.json") from exc
            if not isinstance(project, dict):
                raise GalleryPublishError("project.json must be an object")

            bundle_title, bundle_description = _gallery_title_description(project)
    except zipfile.BadZipFile as exc:
        raise GalleryPublishError("file is not a valid zip archive") from exc

    final_title = title if title is not None else bundle_title
    final_description = description if description is not None else bundle_description

    return _write_gallery_starter_files(
        category=category,
        slug=slug,
        thumb_src=thumb_src,
        gallery_root=gallery_root,
        bundle_src=bundle_path,
        title=final_title,
        description=final_description,
    )


def load_project_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GalleryPublishError(f"invalid project json: {path}") from exc
    if not isinstance(data, dict):
        raise GalleryPublishError("project json must be an object")
    return data
