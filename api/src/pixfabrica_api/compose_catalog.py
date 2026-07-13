"""Catalog helpers for compose agent tools."""

from __future__ import annotations

from typing import Any

from pixfabrica_api.catalog_cache import CatalogCache, get_catalog_cache
from pixfabrica_api.catalog_config import load_excluded_licenses
from pixfabrica_api.license_policy import apply_license_restrictions_to_clip_item
from pixfabrica_api.server_config import DEFAULT_LOCALE
from pixfabrica_core.catalog import (
    TrackKind,
    get_catalog_detail,
    list_catalog_items,
    resolve_clip_description,
    resolve_clip_label,
)


def _catalog_defaults(cache: CatalogCache, clip_type: str) -> dict[str, Any]:
    detail = cache.details.get(clip_type)
    if detail is None or not isinstance(detail.defaults, dict):
        return {}
    return detail.defaults


def _summarize_parameters_schema(schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return {}
    summary: dict[str, dict[str, Any]] = {}
    for name, prop in properties.items():
        if not isinstance(prop, dict):
            continue
        entry: dict[str, Any] = {}
        if "type" in prop:
            entry["type"] = prop["type"]
        if isinstance(prop.get("description"), str) and prop["description"].strip():
            entry["description"] = prop["description"].strip()[:160]
        if isinstance(prop.get("enum"), list):
            entry["enum"] = prop["enum"][:12]
        if entry:
            summary[name] = entry
    return summary


def list_catalog_clips_for_compose(
    *,
    track_kind: str | None = None,
    category: str | None = None,
    lang: str = DEFAULT_LOCALE,
) -> dict[str, Any]:
    cache = get_catalog_cache()
    kind: TrackKind | None = None
    if track_kind in ("skia", "gl", "post"):
        kind = track_kind  # type: ignore[assignment]

    items = list_catalog_items(cache, lang=lang, track_kind=kind)
    excluded = load_excluded_licenses()
    clips: list[dict[str, Any]] = []
    for item in items:
        if category and item.category != category:
            continue
        item = apply_license_restrictions_to_clip_item(item, excluded_licenses=excluded)
        clips.append(
            {
                "clip_type": item.clip_type,
                "label": item.label,
                "description": item.description,
                "track_kind": item.track_kind,
                "category": item.category,
                "tags": item.tags,
                "license": item.license,
                "disabled": item.disabled,
                "restricted_reason": item.restricted_reason,
                "defaults": _catalog_defaults(cache, item.clip_type),
            }
        )
    return {"ok": True, "count": len(clips), "clips": clips}


def get_clip_detail_for_compose(clip_type: str, *, lang: str = DEFAULT_LOCALE) -> dict[str, Any]:
    cache = get_catalog_cache()
    row = next((n for n in cache.clips if n.clip_type == clip_type), None)
    if row is None:
        return {"ok": False, "errors": [f"unknown clip type: {clip_type}"]}

    detail = get_catalog_detail(cache, clip_type, lang=lang)
    if detail is None:
        return {"ok": False, "errors": [f"no catalog detail for clip type: {clip_type}"]}

    description = resolve_clip_description(row.nls, lang, clip_type, row.description_fallback)
    return {
        "ok": True,
        "clip_type": clip_type,
        "label": resolve_clip_label(row.nls, lang, clip_type),
        "description": description,
        "track_kind": row.track_kind,
        "category": row.category,
        "tags": list(row.tags),
        "defaults": detail.defaults,
        "parameters": _summarize_parameters_schema(detail.parameters_schema),
    }
