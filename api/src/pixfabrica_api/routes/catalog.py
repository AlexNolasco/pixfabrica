"""Catalog endpoints for the web plugin picker."""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from pixfabrica_api.catalog_cache import get_catalog_cache, rebuild_catalog_cache
from pixfabrica_api.catalog_config import load_excluded_licenses
from pixfabrica_api.gl_policy import gl_available
from pixfabrica_api.license_policy import (
    apply_license_restrictions_to_clip_item,
    apply_license_restrictions_to_effect_item,
    catalog_item_payload,
)
from pixfabrica_api.server_config import DEFAULT_LOCALE
from pixfabrica_core.catalog import (
    EffectBackend,
    TrackKind,
    get_catalog_detail,
    get_effect_catalog_detail,
    list_catalog_items,
    list_effect_catalog_items,
)
from pixfabrica_core.catalog_ui import find_non_json_serializable_default

router = APIRouter(prefix="/catalog", tags=["catalog"])


class CatalogClipDetailResponse(BaseModel):
    clip_type: str
    plugin_id: str
    ui: dict[str, Any]
    defaults: dict[str, Any]
    parameters_schema: dict[str, Any]
    labels: dict[str, Any]


class CatalogClipInfo(BaseModel):
    clip_type: str
    label: str
    description: str
    icon: str
    track_kind: TrackKind
    category: str
    tags: list[str]
    plugin_id: str
    disabled: bool
    pinned: bool
    license: str
    restricted_reason: str | None = None


LangQuery = Annotated[str, Query(description="BCP-47 locale tag")]
TrackKindQuery = Annotated[TrackKind | None, Query()]
EffectBackendQuery = Annotated[EffectBackend | None, Query()]


def _gl_catalog_disabled(
    *,
    track_kind: TrackKind | None = None,
    effect_backend: EffectBackend | None = None,
) -> bool:
    if gl_available():
        return False
    if track_kind in ("gl", "post"):
        return True
    return effect_backend == "gl"


class CatalogEffectInfo(BaseModel):
    effect_type: str
    label: str
    description: str
    icon: str
    effect_backend: EffectBackend
    category: str
    tags: list[str]
    plugin_id: str
    disabled: bool
    pinned: bool
    license: str
    restricted_reason: str | None = None


def _finalize_clip_catalog_item(item) -> CatalogClipInfo:
    excluded = load_excluded_licenses()
    item = apply_license_restrictions_to_clip_item(item, excluded_licenses=excluded)
    payload = catalog_item_payload(item)
    if _gl_catalog_disabled(track_kind=item.track_kind):
        payload["disabled"] = True
    return CatalogClipInfo.model_validate(payload)


def _finalize_effect_catalog_item(item) -> CatalogEffectInfo:
    excluded = load_excluded_licenses()
    item = apply_license_restrictions_to_effect_item(item, excluded_licenses=excluded)
    payload = catalog_item_payload(item)
    if _gl_catalog_disabled(effect_backend=item.effect_backend):
        payload["disabled"] = True
    return CatalogEffectInfo.model_validate(payload)


def _list_catalog_clips(
    *,
    lang: str,
    track_kind: TrackKind | None,
) -> list[CatalogClipInfo]:
    cache = get_catalog_cache()
    items = list_catalog_items(cache, lang=lang, track_kind=track_kind)
    return [_finalize_clip_catalog_item(item) for item in items]


def _get_catalog_clip_detail(*, clip_type: str, lang: str) -> CatalogClipDetailResponse:
    cache = get_catalog_cache()
    detail = get_catalog_detail(cache, clip_type, lang=lang)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Unknown clip type '{clip_type}'")
    payload = asdict(detail)
    if payload.get("labels") is None:
        payload["labels"] = {"sections": {}, "fields": {}}
    bad = find_non_json_serializable_default(payload.get("defaults") or {})
    if bad is not None:
        field_name, value, exc = bad
        raise HTTPException(
            status_code=500,
            detail=(
                f"Clip '{clip_type}' parameter default '{field_name}' "
                f"is not JSON-serializable ({type(value).__name__}): {exc}"
            ),
        ) from exc
    return CatalogClipDetailResponse.model_validate(payload)


@router.get("/clips", response_model=list[CatalogClipInfo])
async def list_catalog_clips(
    lang: LangQuery = DEFAULT_LOCALE,
    track_kind: TrackKindQuery = None,
) -> list[CatalogClipInfo]:
    return _list_catalog_clips(lang=lang, track_kind=track_kind)


@router.get("/clips/{clip_type}", response_model=CatalogClipDetailResponse)
async def get_catalog_clip(
    clip_type: str,
    lang: LangQuery = DEFAULT_LOCALE,
) -> CatalogClipDetailResponse:
    return _get_catalog_clip_detail(clip_type=clip_type, lang=lang)


@router.get("/effects", response_model=list[CatalogEffectInfo])
async def list_catalog_effects(
    lang: LangQuery = DEFAULT_LOCALE,
    effect_backend: EffectBackendQuery = None,
) -> list[CatalogEffectInfo]:
    cache = get_catalog_cache()
    items = list_effect_catalog_items(cache, lang=lang, effect_backend=effect_backend)
    return [_finalize_effect_catalog_item(item) for item in items]


@router.get("/effects/{effect_type}", response_model=CatalogClipDetailResponse)
async def get_catalog_effect(
    effect_type: str,
    lang: LangQuery = DEFAULT_LOCALE,
) -> CatalogClipDetailResponse:
    cache = get_catalog_cache()
    detail = get_effect_catalog_detail(cache, effect_type, lang=lang)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Unknown effect type '{effect_type}'")
    payload = asdict(detail)
    if payload.get("labels") is None:
        payload["labels"] = {"sections": {}, "fields": {}}
    bad = find_non_json_serializable_default(payload.get("defaults") or {})
    if bad is not None:
        field_name, value, exc = bad
        raise HTTPException(
            status_code=500,
            detail=(
                f"Effect '{effect_type}' parameter default '{field_name}' "
                f"is not JSON-serializable ({type(value).__name__}): {exc}"
            ),
        ) from exc
    return CatalogClipDetailResponse.model_validate(payload)


@router.post("/rebuild")
async def rebuild_catalog() -> dict[str, int]:
    cache = rebuild_catalog_cache()
    clip_count = len(cache.clips)
    return {
        "clip_count": clip_count,
        "node_count": clip_count,
        "effect_count": len(cache.effects),
    }
