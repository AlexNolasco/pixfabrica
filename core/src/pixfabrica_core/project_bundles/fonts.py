"""Collect custom font files referenced by project typography for bundle export."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pixfabrica_core.fonts.catalog import resolve_font_file
from pixfabrica_core.fonts.manifest import load_manifest
from pixfabrica_core.fonts.paths import (
    default_bundled_fonts_dir,
    default_manifest_path,
    woff2_path_for_source,
)
from pixfabrica_core.project_bundles.format import ASSETS_DIR

FONTS_ASSET_DIR = f"{ASSETS_DIR}/fonts"


def bundled_manifest_sources() -> frozenset[str]:
    fonts_dir = default_bundled_fonts_dir()
    manifest_path = default_manifest_path(fonts_dir)
    if not manifest_path.is_file():
        return frozenset()
    manifest = load_manifest(manifest_path)
    return frozenset(weight.source for family in manifest.families for weight in family.weights)


def _nearest_weight_value(weights: list[int], weight: int) -> int:
    return min(weights, key=lambda w: (abs(w - weight), w))


def _typography_family_weights(project: dict[str, Any]) -> dict[str, set[int]]:
    typography = project.get("typography")
    if not isinstance(typography, dict):
        return {}

    by_family: dict[str, set[int]] = {}
    for spec in typography.values():
        if not isinstance(spec, dict):
            continue
        family = spec.get("family")
        weight = spec.get("weight")
        if not isinstance(family, str) or not family.strip():
            continue
        if not isinstance(weight, int):
            continue
        by_family.setdefault(family.strip(), set()).add(weight)
    return by_family


def collect_export_font_paths(project: dict[str, Any]) -> list[Path]:
    """Return on-disk font files (sources + woff2) to embed for custom typography."""
    from pixfabrica_core.fonts import get_font_catalog

    catalog = get_font_catalog()
    manifest_sources = bundled_manifest_sources()
    family_weights = _typography_family_weights(project)
    if not family_weights:
        return []

    paths: list[Path] = []
    seen: set[Path] = set()

    for family, weights in family_weights.items():
        entry = next((item for item in catalog if item.family == family), None)
        if entry is None:
            continue
        catalog_weights = [weight.value for weight in entry.weights]
        if not catalog_weights:
            continue

        for weight in weights:
            match_value = _nearest_weight_value(catalog_weights, weight)
            match = next((w for w in entry.weights if w.value == match_value), None)
            if match is None or not match.source:
                continue
            if match.source in manifest_sources:
                continue

            source_path = resolve_font_file(match.source)
            if source_path is not None and source_path not in seen:
                seen.add(source_path)
                paths.append(source_path)

            woff2_name = Path(woff2_path_for_source(match.source)).name
            woff2_path = resolve_font_file(woff2_name)
            if woff2_path is not None and woff2_path not in seen:
                seen.add(woff2_path)
                paths.append(woff2_path)

    return paths
