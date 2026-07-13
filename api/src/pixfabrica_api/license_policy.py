"""Hosted API policy for license-restricted catalog components."""

from __future__ import annotations

from dataclasses import asdict, replace
from typing import Any, TypedDict

from fastapi import HTTPException

from pixfabrica_api.catalog_cache import get_catalog_cache
from pixfabrica_api.catalog_config import load_excluded_licenses
from pixfabrica_core.catalog import ClipCatalogListItem, EffectCatalogListItem
from pixfabrica_core.license_policy import (
    LICENSE_RESTRICTED_REASON,
    graph_license_violation,
    is_license_excluded,
)


class LicensePolicyErrorPayload(TypedDict):
    code: str
    detail: str


def apply_license_restrictions_to_clip_item(
    item: ClipCatalogListItem,
    *,
    excluded_licenses: frozenset[str],
) -> ClipCatalogListItem:
    if item.disabled:
        return item
    if not is_license_excluded(item.license, excluded_licenses):
        return item
    return replace(
        item,
        disabled=True,
        restricted_reason=LICENSE_RESTRICTED_REASON,
    )


def apply_license_restrictions_to_effect_item(
    item: EffectCatalogListItem,
    *,
    excluded_licenses: frozenset[str],
) -> EffectCatalogListItem:
    if item.disabled:
        return item
    if not is_license_excluded(item.license, excluded_licenses):
        return item
    return replace(
        item,
        disabled=True,
        restricted_reason=LICENSE_RESTRICTED_REASON,
    )


def catalog_item_payload(item: ClipCatalogListItem | EffectCatalogListItem) -> dict[str, Any]:
    return asdict(item)


def license_graph_violation(graph_data: dict[str, Any]) -> LicensePolicyErrorPayload | None:
    excluded = load_excluded_licenses()
    if not excluded:
        return None
    violation = graph_license_violation(
        graph_data,
        catalog=get_catalog_cache(),
        excluded_licenses=excluded,
    )
    if violation is None:
        return None
    return LicensePolicyErrorPayload(
        code=str(violation["code"]),
        detail=str(violation["detail"]),
    )


def validate_graph_license_policy(graph_data: dict[str, Any]) -> None:
    """Raise HTTPException when the graph uses licenses excluded on this host."""
    violation = license_graph_violation(graph_data)
    if violation is not None:
        raise HTTPException(status_code=422, detail=violation)
