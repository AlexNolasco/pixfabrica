"""Starter composition gallery — folder-backed JSON + thumbnails."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from pixfabrica_api.catalog_cache import get_catalog_cache, rebuild_catalog_cache
from pixfabrica_api.gallery_load import load_gallery_starter_project
from pixfabrica_api.gallery_publish import GalleryPublishError, publish_json_to_gallery
from pixfabrica_api.gallery_scan import (
    GalleryIndex,
    resolve_gallery_thumbnail_path,
    scan_gallery,
)
from pixfabrica_api.gallery_settings import gallery_publish_enabled, gallery_root
from pixfabrica_api.gl_policy import validate_graph_gl_policy
from pixfabrica_api.license_policy import validate_graph_license_policy
from pixfabrica_api.media_settings import media_root, public_base_url
from pixfabrica_api.project_limits import validate_graph_policy

router = APIRouter(prefix="/gallery", tags=["gallery"])

ThumbUpload = Annotated[UploadFile, File()]

_THUMB_MEDIA_TYPES = {
    ".webp": "image/webp",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}


class GalleryItemInfo(BaseModel):
    id: str
    category: str
    title: str
    description: str
    thumbnail_url: str


class GalleryCategoryInfo(BaseModel):
    id: str
    label: str
    items: list[GalleryItemInfo]


class GalleryListResponse(BaseModel):
    categories: list[GalleryCategoryInfo] = Field(default_factory=list)


class GalleryPublishResponse(BaseModel):
    category: str
    slug: str
    gallery_json: str = Field(description="Absolute path to written metadata JSON")
    thumbnail: str = Field(description="Absolute path to written thumbnail")
    gallery_bundle: str | None = Field(
        default=None,
        description="Absolute path to written .pixfabrica.zip when present",
    )
    media_refs: list[str] = Field(default_factory=list)


def _thumbnail_url(request: Request, category: str, slug: str) -> str:
    base = public_base_url(request)
    return f"{base}/gallery/thumbnails/{category}/{slug}"


def _build_list_response(request: Request, index: GalleryIndex) -> GalleryListResponse:
    categories: list[GalleryCategoryInfo] = []
    for category in index.categories:
        items = [
            GalleryItemInfo(
                id=item.id,
                category=item.category,
                title=item.title,
                description=item.description,
                thumbnail_url=_thumbnail_url(request, item.category, item.id),
            )
            for item in category.items
        ]
        categories.append(GalleryCategoryInfo(id=category.id, label=category.label, items=items))
    return GalleryListResponse(categories=categories)


@router.get("", response_model=GalleryListResponse)
async def list_gallery(request: Request) -> GalleryListResponse:
    index = scan_gallery(gallery_root())
    return _build_list_response(request, index)


@router.post("/publish", response_model=GalleryPublishResponse)
async def publish_gallery_starter(
    category: Annotated[str, Form()],
    slug: Annotated[str, Form()],
    project: Annotated[str, Form(description="Web project JSON document")],
    thumb: ThumbUpload,
) -> GalleryPublishResponse:
    if not gallery_publish_enabled():
        raise HTTPException(status_code=403, detail="gallery publish is disabled")

    try:
        data = json.loads(project)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="project is not valid JSON") from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="project must be a JSON object")

    validate_graph_gl_policy(data)
    validate_graph_license_policy(data)
    validate_graph_policy(data)

    thumb_suffix = Path(thumb.filename or "thumb.webp").suffix.lower()
    if thumb_suffix not in _THUMB_MEDIA_TYPES:
        raise HTTPException(status_code=400, detail="thumbnail must be .webp, .jpg, .jpeg, or .png")

    thumb_bytes = await thumb.read()
    if not thumb_bytes:
        raise HTTPException(status_code=400, detail="thumbnail is empty")

    with tempfile.NamedTemporaryFile(delete=False, suffix=thumb_suffix) as tmp:
        tmp.write(thumb_bytes)
        thumb_path = Path(tmp.name)

    try:
        catalog = rebuild_catalog_cache()
        result = publish_json_to_gallery(
            data,
            category=category.strip(),
            slug=slug.strip(),
            thumb_src=thumb_path,
            gallery_root=gallery_root(),
            media_root=media_root(),
            catalog=catalog,
        )
    except GalleryPublishError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    finally:
        thumb_path.unlink(missing_ok=True)

    return GalleryPublishResponse(
        category=category.strip(),
        slug=slug.strip(),
        gallery_json=str(result.gallery_json),
        thumbnail=str(result.thumbnail),
        gallery_bundle=str(result.gallery_bundle) if result.gallery_bundle else None,
        media_refs=list(result.media_refs),
    )


@router.get("/thumbnails/{category}/{slug}")
async def get_gallery_thumbnail(category: str, slug: str) -> FileResponse:
    root = gallery_root()
    try:
        path = resolve_gallery_thumbnail_path(root, category, slug)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="thumbnail not found") from exc

    media_type = _THUMB_MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path, media_type=media_type, filename=path.name)


@router.get("/{category}/{slug}")
async def get_gallery_project(category: str, slug: str) -> dict[str, Any]:
    root = gallery_root()
    try:
        resolve_gallery_thumbnail_path(root, category, slug)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="starter not found") from exc

    catalog = get_catalog_cache()
    try:
        return load_gallery_starter_project(
            root,
            category,
            slug,
            media_root=media_root(),
            catalog=catalog,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="starter not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
