"""Pexels stock photo and video search proxy and apply/ingest."""

from __future__ import annotations

import asyncio
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from pixfabrica_api.media_settings import media_root
from pixfabrica_api.pexels_client import (
    PexelsClientError,
    normalize_orientation,
    search_pexels_photos,
    search_pexels_videos,
)
from pixfabrica_api.pexels_ingest import PexelsIngestError, ingest_pexels_photo
from pixfabrica_api.pexels_settings import (
    PEXELS_DEFAULT_PER_PAGE,
    pexels_available,
    pexels_max_per_page,
)
from pixfabrica_api.pexels_video_ingest import PexelsVideoIngestError, ingest_pexels_video
from pixfabrica_api.routes.media import (
    MediaUploadResponse,
    OptimizedForResponse,
    _apply_image_upload_policy,
    _media_upload_response,
    _optimize_video_upload,
    _validate_upload_context,
    _write_upload_manifest,
)
from pixfabrica_api.stock_attribution import StockProvenance, format_stock_attribution

router = APIRouter(prefix="/pexels", tags=["pexels"])

_BACKGROUND_CLIP_TYPE = "std-background-image"
_BACKGROUND_PLUGIN_ID = "pixfabrica-std"
_VIDEO_CLIP_TYPE = "std-video"
_VIDEO_PLUGIN_ID = "pixfabrica-std"

QueryStr = Annotated[str, Query(min_length=1, max_length=200)]
OrientationQuery = Annotated[
    Literal["landscape", "portrait", "square"],
    Query(description="Desired photo orientation"),
]
PageQuery = Annotated[int, Query(ge=1, le=100)]
PerPageQuery = Annotated[int, Query(ge=1, le=80)]
TargetWidthQuery = Annotated[int, Query(gt=0, le=3840)]
TargetHeightQuery = Annotated[int, Query(gt=0, le=2160)]


class PexelsPhotoSrc(BaseModel):
    tiny: str | None = None
    small: str | None = None
    medium: str | None = None
    large: str | None = None
    large2x: str | None = None
    portrait: str | None = None
    landscape: str | None = None
    original: str | None = None


class PexelsPhotoItem(BaseModel):
    id: int
    width: int
    height: int
    alt: str | None = None
    photographer: str
    photographer_url: str
    url: str
    src: PexelsPhotoSrc


class PexelsSearchResponse(BaseModel):
    page: int
    per_page: int
    total_results: int
    next_page: str | None = None
    photos: list[PexelsPhotoItem]


class PexelsApplyRequest(BaseModel):
    src: PexelsPhotoSrc
    orientation: Literal["landscape", "portrait", "square"]
    target_width: int = Field(gt=0, le=3840)
    target_height: int = Field(gt=0, le=2160)
    provenance: StockProvenance | None = None
    clip_type: str | None = Field(
        default=None,
        description="Upload policy clip type (defaults to std-background-image)",
    )
    plugin_id: str | None = Field(
        default=None,
        description="Upload policy plugin id (defaults to pixfabrica-std)",
    )
    field: str = Field(
        default="source",
        min_length=1,
        max_length=120,
        description="Target param field name for upload policy",
    )


class PexelsVideoFileItem(BaseModel):
    id: int | None = None
    quality: str | None = None
    file_type: str | None = None
    width: int
    height: int
    fps: float | None = None
    size: int | None = None
    link: str


class PexelsVideoUserItem(BaseModel):
    id: int | None = None
    name: str
    url: str


class PexelsVideoItem(BaseModel):
    id: int
    width: int
    height: int
    duration: int
    url: str
    image: str
    user: PexelsVideoUserItem
    video_files: list[PexelsVideoFileItem]


class PexelsVideoSearchResponse(BaseModel):
    page: int
    per_page: int
    total_results: int
    next_page: str | None = None
    videos: list[PexelsVideoItem]


class PexelsVideoApplyRequest(BaseModel):
    video_files: list[PexelsVideoFileItem] = Field(min_length=1)
    target_width: int = Field(gt=0, le=3840)
    target_height: int = Field(gt=0, le=2160)
    target_fps: float = Field(gt=0, le=60)
    provenance: StockProvenance | None = None
    clip_type: str | None = Field(
        default=None,
        description="Upload policy clip type (defaults to std-video)",
    )
    plugin_id: str | None = Field(
        default=None,
        description="Upload policy plugin id (defaults to pixfabrica-std)",
    )
    field: str = Field(
        default="source",
        min_length=1,
        max_length=120,
        description="Target param field name for upload policy",
    )


def _attribution_from_provenance(
    provenance: StockProvenance | None,
) -> tuple[str | None, str | None]:
    if provenance is None:
        return None, None
    formatted = format_stock_attribution(provenance)
    if formatted is None:
        return None, None
    return formatted


def _require_pexels() -> None:
    if not pexels_available():
        raise HTTPException(status_code=503, detail="pexels_not_configured")


def _pexels_http_error(exc: PexelsClientError) -> HTTPException:
    message = str(exc)
    if message == "pexels_not_configured":
        return HTTPException(status_code=503, detail=message)
    if message == "pexels_unauthorized":
        return HTTPException(status_code=502, detail=message)
    if message == "pexels_rate_limited":
        retry_after_s = exc.retry_after_s if exc.retry_after_s is not None else 60
        return HTTPException(
            status_code=429,
            detail={"code": message, "retry_after_s": retry_after_s},
        )
    if message == "query is required":
        return HTTPException(status_code=400, detail=message)
    return HTTPException(status_code=502, detail=message)


@router.get("/search", response_model=PexelsSearchResponse)
async def search_stock_photos(
    query: QueryStr,
    orientation: OrientationQuery,
    page: PageQuery = 1,
    per_page: PerPageQuery = PEXELS_DEFAULT_PER_PAGE,
) -> PexelsSearchResponse:
    _require_pexels()
    per_page = min(per_page, pexels_max_per_page())
    try:
        payload = await search_pexels_photos(
            query=query,
            orientation=orientation,
            page=page,
            per_page=per_page,
            size="medium",
        )
    except PexelsClientError as exc:
        raise _pexels_http_error(exc) from exc

    photos: list[PexelsPhotoItem] = []
    for raw in payload["photos"]:
        try:
            photos.append(PexelsPhotoItem.model_validate(raw))
        except Exception:
            continue

    return PexelsSearchResponse(
        page=int(payload.get("page") or page),
        per_page=int(payload.get("per_page") or per_page),
        total_results=int(payload.get("total_results") or 0),
        next_page=payload.get("next_page"),
        photos=photos,
    )


@router.post("/apply", response_model=MediaUploadResponse)
async def apply_stock_photo(request: Request, body: PexelsApplyRequest) -> MediaUploadResponse:
    _require_pexels()
    clip_type = body.clip_type or _BACKGROUND_CLIP_TYPE
    plugin_id = body.plugin_id or _BACKGROUND_PLUGIN_ID
    upload_context = _validate_upload_context(clip_type, plugin_id)
    assert upload_context is not None

    root = media_root()
    src_dict = body.src.model_dump()

    try:
        dest = await asyncio.to_thread(
            ingest_pexels_photo,
            src_dict,
            orientation=body.orientation,
            media_root=root,
        )
    except PexelsIngestError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    optimized_for: OptimizedForResponse | None = await _apply_image_upload_policy(
        dest,
        clip_type=upload_context[0],
        plugin_id=upload_context[1],
        field=body.field,
        target_width=body.target_width,
        target_height=body.target_height,
        target_fps=None,
    )

    await _write_upload_manifest(
        dest,
        upload_context=upload_context,
        kind="image",
        optimized_for=optimized_for,
    )

    source_attribution, source_provider = _attribution_from_provenance(body.provenance)
    return _media_upload_response(
        request,
        dest,
        optimized_for=optimized_for,
        source_attribution=source_attribution,
        source_provider=source_provider,
    )


@router.get("/videos/search", response_model=PexelsVideoSearchResponse)
async def search_stock_videos(
    query: QueryStr,
    orientation: OrientationQuery,
    page: PageQuery = 1,
    per_page: PerPageQuery = PEXELS_DEFAULT_PER_PAGE,
) -> PexelsVideoSearchResponse:
    _require_pexels()
    per_page = min(per_page, pexels_max_per_page())
    try:
        payload = await search_pexels_videos(
            query=query,
            orientation=orientation,
            page=page,
            per_page=per_page,
        )
    except PexelsClientError as exc:
        raise _pexels_http_error(exc) from exc

    videos: list[PexelsVideoItem] = []
    for raw in payload["videos"]:
        try:
            videos.append(PexelsVideoItem.model_validate(raw))
        except Exception:
            continue

    return PexelsVideoSearchResponse(
        page=int(payload.get("page") or page),
        per_page=int(payload.get("per_page") or per_page),
        total_results=int(payload.get("total_results") or 0),
        next_page=payload.get("next_page"),
        videos=videos,
    )


@router.post("/videos/apply", response_model=MediaUploadResponse)
async def apply_stock_video(request: Request, body: PexelsVideoApplyRequest) -> MediaUploadResponse:
    _require_pexels()
    clip_type = body.clip_type or _VIDEO_CLIP_TYPE
    plugin_id = body.plugin_id or _VIDEO_PLUGIN_ID
    upload_context = _validate_upload_context(clip_type, plugin_id)
    assert upload_context is not None

    root = media_root()
    video_files = [entry.model_dump() for entry in body.video_files]

    try:
        dest = await asyncio.to_thread(
            ingest_pexels_video,
            video_files,
            target_width=body.target_width,
            target_height=body.target_height,
            media_root=root,
        )
    except PexelsVideoIngestError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        result = await _optimize_video_upload(
            dest,
            target_width=body.target_width,
            target_height=body.target_height,
            target_fps=body.target_fps,
        )
    except HTTPException:
        raise
    except Exception as exc:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    dest = result.path
    optimized_for = OptimizedForResponse(
        width=result.optimized_for.width,
        height=result.optimized_for.height,
        fps=result.optimized_for.fps,
    )

    await _write_upload_manifest(
        dest,
        upload_context=upload_context,
        kind="video",
        optimized_for=optimized_for,
    )

    source_attribution, source_provider = _attribution_from_provenance(body.provenance)
    return _media_upload_response(
        request,
        dest,
        optimized_for=optimized_for,
        source_attribution=source_attribution,
        source_provider=source_provider,
    )


@router.get("/orientation")
async def resolve_orientation(
    width: TargetWidthQuery,
    height: TargetHeightQuery,
) -> dict[str, str]:
    return {"orientation": normalize_orientation(width, height)}
