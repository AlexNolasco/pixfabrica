"""Scan media/gallery/ for starter bundles + thumbnails."""

from __future__ import annotations

import json
import logging
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

from pixfabrica_core.project_bundles.format import PROJECT_JSON_NAME

log = logging.getLogger("pixfabrica.api.gallery")

_THUMB_EXTENSIONS = (".webp", ".jpg", ".jpeg", ".png")
_SLUG_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
_GALLERY_BUNDLE_SUFFIX = ".pixfabrica.zip"
_PROJECT_FIELD_KEYS = frozenset(
    {"tracks", "sounds", "width", "height", "fps", "duration", "schema_version"}
)


@dataclass(frozen=True)
class GalleryItemSummary:
    id: str
    category: str
    title: str
    description: str


@dataclass(frozen=True)
class GalleryCategory:
    id: str
    label: str
    items: tuple[GalleryItemSummary, ...]


@dataclass(frozen=True)
class GalleryIndex:
    categories: tuple[GalleryCategory, ...]


def humanize_slug(slug: str) -> str:
    return slug.replace("_", " ").replace("-", " ").strip().title()


def gallery_bundle_filename(slug: str) -> str:
    return f"{slug}{_GALLERY_BUNDLE_SUFFIX}"


def _valid_slug(name: str) -> bool:
    return bool(name and _SLUG_PATTERN.match(name))


def _find_thumbnail(category_dir: Path, slug: str) -> Path | None:
    for ext in _THUMB_EXTENSIONS:
        candidate = category_dir / f"{slug}{ext}"
        if candidate.is_file():
            return candidate
    return None


def _is_metadata_json(data: dict[str, object]) -> bool:
    return not any(key in data for key in _PROJECT_FIELD_KEYS)


def _title_description_from_dict(
    data: dict[str, object],
    slug: str,
) -> tuple[str, str]:
    title_raw = data.get("title")
    title = str(title_raw).strip() if title_raw is not None else ""
    if not title:
        title = humanize_slug(slug)
    description_raw = data.get("description")
    description = str(description_raw).strip() if description_raw is not None else ""
    return title, description


def _read_project_json_from_bundle(bundle_path: Path) -> dict[str, object] | None:
    try:
        with zipfile.ZipFile(bundle_path) as archive:
            raw = archive.read(PROJECT_JSON_NAME)
            data = json.loads(raw)
    except (OSError, KeyError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        log.warning("gallery bundle unreadable: %s: %s", bundle_path, exc)
        return None
    if not isinstance(data, dict):
        log.warning("gallery bundle project.json must be an object: %s", bundle_path)
        return None
    return data


def _list_metadata(
    category_dir: Path,
    slug: str,
    bundle_path: Path | None,
) -> tuple[str, str] | None:
    json_path = category_dir / f"{slug}.json"
    if json_path.is_file():
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("gallery metadata json invalid: %s/%s: %s", category_dir.name, slug, exc)
            return None
        if not isinstance(data, dict):
            log.warning("gallery metadata json must be an object: %s/%s", category_dir.name, slug)
            return None
        if bundle_path is not None and not _is_metadata_json(data):
            log.warning(
                "gallery item has bundle and full project json; using bundle for list metadata: %s/%s",
                category_dir.name,
                slug,
            )
        return _title_description_from_dict(data, slug)

    if bundle_path is not None:
        project = _read_project_json_from_bundle(bundle_path)
        if project is not None:
            return _title_description_from_dict(project, slug)
    return None


def resolve_gallery_bundle_path(root: Path, category: str, slug: str) -> Path:
    if not _valid_slug(category) or not _valid_slug(slug):
        raise ValueError("invalid gallery path segment")
    path = (root / category / gallery_bundle_filename(slug)).resolve()
    if not str(path).startswith(str(root.resolve())):
        raise ValueError("gallery path escapes root")
    return path


def resolve_gallery_project_path(root: Path, category: str, slug: str) -> Path:
    if not _valid_slug(category) or not _valid_slug(slug):
        raise ValueError("invalid gallery path segment")
    path = (root / category / f"{slug}.json").resolve()
    if not str(path).startswith(str(root.resolve())):
        raise ValueError("gallery path escapes root")
    return path


def resolve_gallery_thumbnail_path(root: Path, category: str, slug: str) -> Path:
    if not _valid_slug(category) or not _valid_slug(slug):
        raise ValueError("invalid gallery path segment")
    category_dir = (root / category).resolve()
    if not str(category_dir).startswith(str(root.resolve())):
        raise ValueError("gallery path escapes root")
    thumb = _find_thumbnail(category_dir, slug)
    if thumb is None:
        raise FileNotFoundError(f"thumbnail not found for {category}/{slug}")
    return thumb


def _starter_slugs(category_dir: Path) -> set[str]:
    slugs: set[str] = set()
    for path in category_dir.glob(f"*{_GALLERY_BUNDLE_SUFFIX}"):
        stem = path.name[: -len(_GALLERY_BUNDLE_SUFFIX)]
        if _valid_slug(stem):
            slugs.add(stem)
    for path in category_dir.glob("*.json"):
        if _valid_slug(path.stem):
            slugs.add(path.stem)
    return slugs


def scan_gallery(root: Path) -> GalleryIndex:
    if not root.is_dir():
        return GalleryIndex(categories=())

    root = root.resolve()
    categories: list[GalleryCategory] = []
    for category_dir in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if not category_dir.is_dir():
            continue
        category_id = category_dir.name
        if not _valid_slug(category_id):
            log.warning("skipping gallery category with invalid name: %s", category_id)
            continue

        items: list[GalleryItemSummary] = []
        for slug in sorted(_starter_slugs(category_dir), key=str.lower):
            if _find_thumbnail(category_dir, slug) is None:
                log.warning("gallery item missing thumbnail: %s/%s", category_id, slug)
                continue

            bundle_path = category_dir / gallery_bundle_filename(slug)
            bundle = bundle_path if bundle_path.is_file() else None
            json_path = category_dir / f"{slug}.json"

            if bundle is None and not json_path.is_file():
                log.warning("gallery item missing bundle or json: %s/%s", category_id, slug)
                continue

            meta = _list_metadata(category_dir, slug, bundle)
            if meta is None:
                continue
            title, description = meta

            items.append(
                GalleryItemSummary(
                    id=slug,
                    category=category_id,
                    title=title,
                    description=description,
                )
            )

        if items:
            categories.append(
                GalleryCategory(
                    id=category_id,
                    label=humanize_slug(category_id),
                    items=tuple(items),
                )
            )

    return GalleryIndex(categories=tuple(categories))
