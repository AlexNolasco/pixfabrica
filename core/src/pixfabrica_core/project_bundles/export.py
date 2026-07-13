"""Build a portable .pixfabrica.zip from a web project document."""

from __future__ import annotations

import copy
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path
from typing import Any

from pixfabrica_core.audio.bundle_analysis import (
    collect_analysis_sidecars_for_export,
    default_cache_dir,
    sound_analysis_specs_for_bundled_sounds,
)
from pixfabrica_core.catalog import CatalogCache
from pixfabrica_core.media_upload import sanitize_upload_basename
from pixfabrica_core.project_bundles.errors import BundleExportError
from pixfabrica_core.project_bundles.fonts import FONTS_ASSET_DIR, collect_export_font_paths
from pixfabrica_core.project_bundles.format import (
    ASSETS_DIR,
    BUNDLE_MANIFEST_NAME,
    HOST_LOCAL_FIELDS,
    PROJECT_JSON_NAME,
    bundle_manifest,
)
from pixfabrica_core.project_bundles.refs import (
    MediaRef,
    collect_media_refs,
    resolve_local_media_path,
    set_json_value,
)

_INVALID_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|]')


def export_filename_from_title(title: str) -> str:
    trimmed = title.strip()
    base = trimmed if trimmed else "untitled"
    safe = _INVALID_FILENAME_CHARS.sub("", base).strip()
    return f"{safe or 'untitled'}.pixfabrica.zip"


def strip_host_local_fields(project: dict[str, Any]) -> None:
    for key in HOST_LOCAL_FIELDS:
        project.pop(key, None)


def _plan_asset_names(resolved_refs: list[tuple[MediaRef, Path]]) -> dict[Path, str]:
    path_to_asset: dict[Path, str] = {}
    content_to_asset: dict[str, str] = {}
    used_names: dict[str, Path] = {}

    for ref, path in resolved_refs:
        if path in path_to_asset:
            continue

        content_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if content_hash in content_to_asset:
            path_to_asset[path] = content_to_asset[content_hash]
            continue

        base = sanitize_upload_basename(path.name)
        stem = Path(base).stem
        suffix = Path(base).suffix
        name = base
        counter = 2
        while name in used_names and used_names[name] != path:
            name = f"{stem}-{counter}{suffix}"
            counter += 1

        used_names[name] = path
        if ref.path_parts and ref.path_parts[0] == "fonts":
            asset_rel = f"{FONTS_ASSET_DIR}/{name}"
        else:
            asset_rel = f"{ASSETS_DIR}/{name}"
        path_to_asset[path] = asset_rel
        content_to_asset[content_hash] = asset_rel

    return path_to_asset


def export_project_bundle(
    project: dict[str, Any],
    *,
    media_root: Path,
    catalog: CatalogCache,
) -> tuple[bytes, str]:
    """Return ``(zip_bytes, download_filename)``."""
    if not isinstance(project, dict):
        raise BundleExportError(missing_files=["<invalid project document>"])

    work = copy.deepcopy(project)
    strip_host_local_fields(work)

    refs = collect_media_refs(work, catalog)
    missing_files: list[str] = []
    resolved_refs: list[tuple[MediaRef, Path]] = []
    seen_missing: set[str] = set()

    for ref in refs:
        resolved = resolve_local_media_path(ref.source_value, media_root)
        if resolved is None:
            if ref.source_value not in seen_missing:
                seen_missing.add(ref.source_value)
                missing_files.append(ref.source_value)
            continue
        resolved_refs.append((ref, resolved))

    for font_path in collect_export_font_paths(work):
        if not font_path.is_file():
            if str(font_path) not in seen_missing:
                seen_missing.add(str(font_path))
                missing_files.append(str(font_path))
            continue
        resolved_refs.append((MediaRef(("fonts", font_path.name), str(font_path)), font_path))

    if missing_files:
        raise BundleExportError(missing_files=sorted(missing_files))

    path_to_asset = _plan_asset_names(resolved_refs)
    for ref, path in resolved_refs:
        if ref.path_parts and ref.path_parts[0] == "fonts":
            continue
        set_json_value(work, ref.path_parts, path_to_asset[path])

    sound_asset_paths: dict[int, tuple[Path, str]] = {}
    for ref, path in resolved_refs:
        parts = ref.path_parts
        if (
            len(parts) == 3
            and parts[0] == "sounds"
            and isinstance(parts[1], int)
            and parts[2] == "source"
        ):
            sound_asset_paths[parts[1]] = (path, path_to_asset[path])

    analysis_specs = sound_analysis_specs_for_bundled_sounds(work, sound_asset_paths)
    analysis_manifest, analysis_files = collect_analysis_sidecars_for_export(
        analysis_specs,
        cache_dir=default_cache_dir(),
    )

    title = work.get("title")
    download_name = export_filename_from_title(title if isinstance(title, str) else "")

    buffer = io.BytesIO()
    unique_assets = sorted(set(path_to_asset.values()))
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            BUNDLE_MANIFEST_NAME,
            json.dumps(
                bundle_manifest(
                    asset_count=len(unique_assets),
                    analysis=analysis_manifest or None,
                ),
                indent=2,
            )
            + "\n",
        )
        archive.writestr(PROJECT_JSON_NAME, json.dumps(work, indent=2) + "\n")
        written: set[str] = set()
        for path, asset_rel in path_to_asset.items():
            if asset_rel in written:
                continue
            archive.write(path, asset_rel)
            written.add(asset_rel)
        for zip_path, npz_path in analysis_files:
            archive.write(npz_path, zip_path)

    return buffer.getvalue(), download_name
