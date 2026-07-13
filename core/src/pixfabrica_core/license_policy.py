"""License metadata and graph policy for catalog filtering."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pixfabrica_core.catalog import CatalogCache

DEFAULT_PLUGIN_LICENSE = "MIT"
LICENSE_RESTRICTED_REASON = "license"
LICENSE_UNAVAILABLE_CODE = "license_unavailable"

_LICENSE_UNAVAILABLE_DETAIL = (
    "This project uses components whose licenses are excluded on this host."
)


def resolve_clip_license(clip_cls: type, plugin_license: str) -> str:
    """Return SPDX license for a clip or effect class (override or plugin default)."""
    override = getattr(clip_cls, "clip_license", None)
    if isinstance(override, str) and override.strip():
        return override.strip()
    if plugin_license.strip():
        return plugin_license.strip()
    return DEFAULT_PLUGIN_LICENSE


def resolve_plugin_license(manifest: object | None) -> str:
    if manifest is None:
        return DEFAULT_PLUGIN_LICENSE
    license_value = getattr(manifest, "license", None)
    if isinstance(license_value, str) and license_value.strip():
        return license_value.strip()
    return DEFAULT_PLUGIN_LICENSE


def is_license_excluded(license_value: str, excluded: frozenset[str]) -> bool:
    if not excluded:
        return False
    return license_value in excluded


def catalog_license_index(cache: CatalogCache) -> dict[str, str]:
    index: dict[str, str] = {}
    for clip in cache.clips:
        index[clip.clip_type] = clip.license
    for effect in cache.effects:
        index[effect.effect_type] = effect.license
    return index


def iter_graph_clip_types(graph: dict[str, Any]) -> list[str]:
    """Collect enabled clip and effect types from render/web graph JSON."""
    types: list[str] = []
    tracks = graph.get("tracks")
    if not isinstance(tracks, list):
        return types

    for track in tracks:
        if not isinstance(track, dict) or track.get("enabled") is False:
            continue
        clips = track.get("clips")
        if not isinstance(clips, list):
            continue
        for clip in clips:
            if not isinstance(clip, dict) or clip.get("enabled") is False:
                continue
            clip_type_value = clip.get("clip_type")
            if isinstance(clip_type_value, str) and clip_type_value.strip():
                types.append(clip_type_value.strip())
            effects = clip.get("effects")
            if not isinstance(effects, list):
                continue
            for effect in effects:
                if not isinstance(effect, dict) or effect.get("enabled") is False:
                    continue
                fx_type = effect.get("effect_type")
                if isinstance(fx_type, str) and fx_type.strip():
                    types.append(fx_type.strip())
    return types


def graph_license_violation(
    graph_data: dict[str, Any],
    *,
    catalog: CatalogCache,
    excluded_licenses: frozenset[str],
) -> dict[str, Any] | None:
    """Return a policy error payload when the graph uses excluded licenses."""
    if not excluded_licenses:
        return None

    license_index = catalog_license_index(catalog)
    blocked: list[dict[str, str]] = []
    seen: set[str] = set()

    for clip_type in iter_graph_clip_types(graph_data):
        if clip_type in seen:
            continue
        license_value = license_index.get(clip_type)
        if license_value is None or not is_license_excluded(license_value, excluded_licenses):
            continue
        seen.add(clip_type)
        blocked.append({"clip_type": clip_type, "license": license_value})

    if not blocked:
        return None

    parts = [f"{item['clip_type']} ({item['license']})" for item in blocked]
    detail = f"{_LICENSE_UNAVAILABLE_DETAIL} Blocked: {', '.join(parts)}."
    return {
        "code": LICENSE_UNAVAILABLE_CODE,
        "detail": detail,
        "blocked": blocked,
    }
