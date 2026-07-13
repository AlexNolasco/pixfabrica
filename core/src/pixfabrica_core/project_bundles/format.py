"""Bundle archive layout and manifest."""

from __future__ import annotations

from typing import Any

from pixfabrica_core.audio.bundle_analysis import ANALYSIS_DIR

BUNDLE_FORMAT = "pixfabrica-bundle"
BUNDLE_FORMAT_VERSION = 1
BUNDLE_MANIFEST_NAME = "bundle.json"
PROJECT_JSON_NAME = "project.json"
ASSETS_DIR = "assets"
HOST_LOCAL_FIELDS = frozenset({"import_bundle_id"})


def bundle_manifest(
    *,
    asset_count: int,
    analysis: list[dict[str, Any]] | None = None,
) -> dict[str, object]:
    manifest: dict[str, object] = {
        "format": BUNDLE_FORMAT,
        "format_version": BUNDLE_FORMAT_VERSION,
        "project": PROJECT_JSON_NAME,
        "assets_dir": ASSETS_DIR,
        "asset_count": asset_count,
    }
    if analysis:
        manifest["analysis_dir"] = ANALYSIS_DIR
        manifest["analysis"] = analysis
    return manifest


def validate_bundle_manifest(data: object) -> None:
    if not isinstance(data, dict):
        raise ValueError("bundle manifest must be an object")
    if data.get("format") != BUNDLE_FORMAT:
        raise ValueError(f"unsupported bundle format: {data.get('format')!r}")
    version = data.get("format_version")
    if version != BUNDLE_FORMAT_VERSION:
        raise ValueError(f"unsupported bundle format_version: {version!r}")
    if data.get("project") != PROJECT_JSON_NAME:
        raise ValueError("bundle manifest project entry mismatch")
    if data.get("assets_dir") != ASSETS_DIR:
        raise ValueError("bundle manifest assets_dir entry mismatch")
