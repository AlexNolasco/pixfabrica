"""Extract a .pixfabrica.zip and rewrite bundled asset paths for this host."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from pixfabrica_core.audio.bundle_analysis import (
    ANALYSIS_DIR,
    default_cache_dir,
    hydrate_analysis_cache_from_manifest,
)
from pixfabrica_core.catalog import CatalogCache
from pixfabrica_core.fonts.install import install_fonts_from_directory
from pixfabrica_core.media_upload import resolve_media_path
from pixfabrica_core.project_bundles.errors import BundleImportError
from pixfabrica_core.project_bundles.format import (
    ASSETS_DIR,
    BUNDLE_MANIFEST_NAME,
    PROJECT_JSON_NAME,
    validate_bundle_manifest,
)
from pixfabrica_core.project_bundles.refs import (
    collect_media_refs,
    is_remote_source,
    set_json_value,
)


def _is_safe_zip_name(name: str) -> bool:
    path = PurePosixPath(name)
    if path.is_absolute():
        return False
    return ".." not in path.parts


def _bundled_path_to_local(value: str, bundle_dir: Path) -> str:
    prefix = f"{ASSETS_DIR}/"
    if not value.startswith(prefix):
        return value
    rel = value[len(prefix) :]
    try:
        resolved = resolve_media_path(bundle_dir, rel)
    except ValueError as exc:
        raise BundleImportError(f"invalid bundled asset path: {value}") from exc
    return str(resolved.resolve())


def import_project_bundle(
    zip_bytes: bytes,
    *,
    bundle_dir: Path,
    catalog: CatalogCache,
    assign_import_bundle_id: bool = False,
    import_bundle_id: str | None = None,
) -> dict[str, Any]:
    """Extract bundle bytes into ``bundle_dir`` and return rewritten project JSON."""
    bundle_dir = bundle_dir.resolve()
    bundle_dir.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
            for name in archive.namelist():
                if not _is_safe_zip_name(name):
                    raise BundleImportError(f"unsafe zip entry: {name}")

            try:
                manifest_raw = json.loads(archive.read(BUNDLE_MANIFEST_NAME))
            except KeyError as exc:
                raise BundleImportError("bundle missing bundle.json") from exc
            except json.JSONDecodeError as exc:
                raise BundleImportError("bundle.json is not valid JSON") from exc

            try:
                validate_bundle_manifest(manifest_raw)
            except ValueError as exc:
                raise BundleImportError(str(exc)) from exc

            try:
                project_raw = archive.read(PROJECT_JSON_NAME)
            except KeyError as exc:
                raise BundleImportError("bundle missing project.json") from exc

            try:
                project = json.loads(project_raw)
            except json.JSONDecodeError as exc:
                raise BundleImportError("project.json is not valid JSON") from exc

            if not isinstance(project, dict):
                raise BundleImportError("project.json must be an object")

            asset_entries = [
                name
                for name in archive.namelist()
                if name.startswith(f"{ASSETS_DIR}/") and not name.endswith("/")
            ]

            for entry in asset_entries:
                rel = PurePosixPath(entry).relative_to(ASSETS_DIR)
                rel_str = rel.as_posix()
                try:
                    target = resolve_media_path(bundle_dir, rel_str)
                except ValueError as exc:
                    raise BundleImportError(f"invalid asset entry: {entry}") from exc
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(entry))

            for ref in collect_media_refs(project, catalog):
                value = ref.source_value
                if is_remote_source(value):
                    continue
                if not value.startswith(f"{ASSETS_DIR}/"):
                    raise BundleImportError(f"project reference is not bundled: {value}")
                local_path = Path(_bundled_path_to_local(value, bundle_dir))
                if not local_path.is_file():
                    raise BundleImportError(f"bundle missing asset: {value}")

            for ref in collect_media_refs(project, catalog):
                value = ref.source_value
                if is_remote_source(value):
                    continue
                set_json_value(project, ref.path_parts, _bundled_path_to_local(value, bundle_dir))

            sidecar_bytes: dict[str, bytes] = {}
            for name in archive.namelist():
                if name.startswith(f"{ANALYSIS_DIR}/") and not name.endswith("/"):
                    if not _is_safe_zip_name(name):
                        raise BundleImportError(f"unsafe zip entry: {name}")
                    sidecar_bytes[name] = archive.read(name)

            hydrate_analysis_cache_from_manifest(
                manifest_raw.get("analysis"),
                bundle_dir=bundle_dir,
                cache_dir=default_cache_dir(),
                sidecar_bytes=sidecar_bytes,
            )

            if assign_import_bundle_id:
                if not import_bundle_id:
                    raise BundleImportError(
                        "import_bundle_id required when assign_import_bundle_id"
                    )
                project["import_bundle_id"] = import_bundle_id

            fonts_dir = bundle_dir / "fonts"
            if fonts_dir.is_dir():
                install_fonts_from_directory(fonts_dir)

            return project
    except zipfile.BadZipFile as exc:
        raise BundleImportError("file is not a valid zip archive") from exc
