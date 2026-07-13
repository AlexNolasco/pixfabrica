"""Upload and serve user media files."""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from pixfabrica_api.audio_transcode import (
    AudioTranscodeError,
    optimize_audio_upload,
)
from pixfabrica_api.audio_transcode import (
    ffmpeg_available as audio_ffmpeg_available,
)
from pixfabrica_api.catalog_cache import get_catalog_cache
from pixfabrica_api.image_transcode import (
    ImageOptimizeError,
    optimize_image_upload,
)
from pixfabrica_api.media_fetch import MediaFetchError, allocate_ingest_path, fetch_url_to_path
from pixfabrica_api.media_settings import media_root, public_base_url
from pixfabrica_api.video_boomerang import create_boomerang_video, is_boomerang_derivative_path
from pixfabrica_api.video_reverse import create_reversed_video
from pixfabrica_api.video_transcode import (
    VideoTranscodeError,
    optimize_video_upload,
)
from pixfabrica_api.video_transcode import (
    ffmpeg_available as video_ffmpeg_available,
)
from pixfabrica_core.audio.content_hash import write_audio_content_sidecar
from pixfabrica_core.catalog import resolve_file_upload_policy, validate_upload_clip_context
from pixfabrica_core.file_upload_policy import UploadPolicyContext
from pixfabrica_core.media_upload import (
    MediaUploadKind,
    is_lossless_audio_filename,
    max_bytes_for_audio_upload,
    max_bytes_for_kind,
    resolve_media_path,
    sanitize_upload_basename,
)
from pixfabrica_core.upload_manifest import read_upload_manifest, write_upload_manifest

router = APIRouter(prefix="/media", tags=["media"])

_VALID_KINDS = frozenset({"audio", "image", "lyrics", "video", "mesh", "default"})

KindQuery = Annotated[
    MediaUploadKind,
    Query(description="Upload category for size limits (audio, image, lyrics, …)"),
]
ClipTypeQuery = Annotated[
    str | None,
    Query(description="Catalog clip type, e.g. std-video"),
]
PluginIdQuery = Annotated[
    str | None,
    Query(description="Plugin package id from catalog, e.g. pixfabrica-std"),
]
TargetWidthQuery = Annotated[
    int | None,
    Query(gt=0, le=3840, description="Project render width for video proxy sizing"),
]
TargetHeightQuery = Annotated[
    int | None,
    Query(gt=0, le=2160, description="Project render height for video proxy sizing"),
]
TargetFpsQuery = Annotated[
    float | None,
    Query(gt=0, le=60, description="Project render fps for video proxy sizing"),
]
FieldQuery = Annotated[
    str,
    Query(description="Clip parameter field name for file upload policy lookup"),
]
FileUpload = Annotated[UploadFile, File()]


class OptimizedForResponse(BaseModel):
    width: int
    height: int
    fps: float


class MediaUploadResponse(BaseModel):
    path: str = Field(description="Absolute path to the stored file on the API host")
    filename: str
    size: int
    url: str = Field(description="HTTP URL to fetch the same file from this API")
    optimized_for: OptimizedForResponse | None = None
    source_attribution: str | None = Field(
        default=None,
        description="Human-readable stock media attribution when apply included provenance",
    )
    source_provider: str | None = Field(
        default=None,
        description="Stock provider id (e.g. pexels) when apply included provenance",
    )


class UploadManifestResponse(BaseModel):
    optimized_for: OptimizedForResponse | None = None


class VideoBoomerangRequest(BaseModel):
    source: str = Field(min_length=1, description="Absolute path to an existing media file")
    start_offset: float = Field(default=0.0, ge=0.0)
    playback_rate: float = Field(default=1.0, gt=0.0, le=5.0)
    max_duration: float = Field(
        gt=0.0, description="Cap output length (typically remaining job time)"
    )
    target_fps: float = Field(default=24.0, gt=0.0, le=60.0)
    target_width: int | None = Field(default=None, gt=0, le=3840)
    target_height: int | None = Field(default=None, gt=0, le=2160)


class VideoBoomerangResponse(BaseModel):
    path: str
    filename: str
    duration: float
    size: int
    url: str
    capped: bool
    optimized_for: OptimizedForResponse | None = None


class VideoReverseRequest(BaseModel):
    source: str = Field(min_length=1, description="Absolute path to an existing media file")
    start_offset: float = Field(default=0.0, ge=0.0)
    playback_rate: float = Field(default=1.0, gt=0.0, le=5.0)
    target_fps: float = Field(default=24.0, gt=0.0, le=60.0)
    target_width: int | None = Field(default=None, gt=0, le=3840)
    target_height: int | None = Field(default=None, gt=0, le=2160)


class VideoReverseResponse(BaseModel):
    path: str
    filename: str
    duration: float
    size: int
    url: str
    optimized_for: OptimizedForResponse | None = None


class IngestUrlRequest(BaseModel):
    url: str = Field(min_length=1, description="http(s) URL to fetch and store locally")


def _validate_upload_context(
    clip_type: str | None,
    plugin_id: str | None,
) -> tuple[str, str] | None:
    has_type = clip_type is not None
    has_plugin = plugin_id is not None
    if not has_type and not has_plugin:
        return None
    if has_type != has_plugin:
        raise HTTPException(
            status_code=400,
            detail="clip_type and plugin_id must be sent together",
        )
    assert clip_type is not None and plugin_id is not None
    cache = get_catalog_cache()
    if not validate_upload_clip_context(cache, clip_type, plugin_id):
        raise HTTPException(
            status_code=400,
            detail=f"unknown clip_type and plugin_id pair: {clip_type!r}, {plugin_id!r}",
        )
    return clip_type, plugin_id


def _optimized_for_payload(response: OptimizedForResponse) -> dict[str, int | float]:
    return {
        "width": response.width,
        "height": response.height,
        "fps": response.fps,
    }


def _upload_policy_context(
    *,
    clip_type: str,
    plugin_id: str,
    field: str,
    kind: str,
    target_width: int | None,
    target_height: int | None,
    target_fps: float | None,
) -> UploadPolicyContext:
    return UploadPolicyContext(
        clip_type=clip_type,
        plugin_id=plugin_id,
        field=field,
        kind=kind,
        target_width=target_width,
        target_height=target_height,
        target_fps=target_fps,
    )


async def _apply_image_upload_policy(
    dest: Path,
    *,
    clip_type: str,
    plugin_id: str,
    field: str,
    target_width: int | None,
    target_height: int | None,
    target_fps: float | None,
) -> OptimizedForResponse | None:
    cache = get_catalog_cache()
    policy = resolve_file_upload_policy(
        cache,
        clip_type=clip_type,
        plugin_id=plugin_id,
        field=field,
    )
    if policy is None:
        return None
    if target_width is None or target_height is None:
        return None

    ctx = _upload_policy_context(
        clip_type=clip_type,
        plugin_id=plugin_id,
        field=field,
        kind="image",
        target_width=target_width,
        target_height=target_height,
        target_fps=target_fps,
    )
    max_px = policy.max_px(ctx)
    try:
        result = await asyncio.to_thread(optimize_image_upload, dest, max_px)
    except ImageOptimizeError as exc:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return OptimizedForResponse(
        width=result.optimized_for.width,
        height=result.optimized_for.height,
        fps=0.0,
    )


def _media_upload_response(
    request: Request,
    dest: Path,
    *,
    optimized_for: OptimizedForResponse | None,
    source_attribution: str | None = None,
    source_provider: str | None = None,
) -> MediaUploadResponse:
    safe_name = dest.name
    data = dest.read_bytes()
    return MediaUploadResponse(
        path=str(dest),
        filename=safe_name,
        size=len(data),
        url=f"{public_base_url(request)}/media/{safe_name}",
        optimized_for=optimized_for,
        source_attribution=source_attribution,
        source_provider=source_provider,
    )


async def _write_upload_manifest(
    dest: Path,
    *,
    upload_context: tuple[str, str] | None,
    kind: str,
    optimized_for: OptimizedForResponse | None,
) -> None:
    data = dest.read_bytes()
    content_sha256 = hashlib.sha256(data).hexdigest()
    size = len(data)

    if kind == "audio":
        write_audio_content_sidecar(dest, content_sha256=content_sha256, size=size)

    if upload_context is None:
        return

    ctx_clip_type, ctx_plugin_id = upload_context
    manifest_optimized = (
        _optimized_for_payload(optimized_for) if optimized_for is not None else None
    )
    write_upload_manifest(
        dest,
        clip_type=ctx_clip_type,
        plugin_id=ctx_plugin_id,
        kind=kind,
        size=size,
        content_sha256=content_sha256,
        optimized_for=manifest_optimized,
    )


async def _optimize_video_upload(
    dest,
    *,
    target_width: int | None,
    target_height: int | None,
    target_fps: float | None,
):
    if not video_ffmpeg_available():
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=503, detail="ffmpeg not available for video upload")

    try:
        return await asyncio.to_thread(
            optimize_video_upload,
            dest,
            target_width=target_width,
            target_height=target_height,
            target_fps=target_fps,
        )
    except VideoTranscodeError as exc:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc


async def _optimize_audio_upload(dest):
    if not audio_ffmpeg_available():
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=503, detail="ffmpeg not available for audio upload")

    try:
        return await asyncio.to_thread(optimize_audio_upload, dest)
    except AudioTranscodeError as exc:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("", response_model=MediaUploadResponse)
async def upload_media(
    request: Request,
    file: FileUpload,
    kind: KindQuery = "default",
    clip_type: ClipTypeQuery = None,
    plugin_id: PluginIdQuery = None,
    field: FieldQuery = "source",
    target_width: TargetWidthQuery = None,
    target_height: TargetHeightQuery = None,
    target_fps: TargetFpsQuery = None,
) -> MediaUploadResponse:
    if kind not in _VALID_KINDS:
        raise HTTPException(status_code=400, detail=f"invalid kind: {kind}")

    upload_context = _validate_upload_context(clip_type, plugin_id)

    original = file.filename or "upload"
    try:
        safe_name = sanitize_upload_basename(original)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    data = await file.read()
    size = len(data)
    limit = max_bytes_for_audio_upload(safe_name) if kind == "audio" else max_bytes_for_kind(kind)
    if size > limit:
        raise HTTPException(
            status_code=413,
            detail=f"file exceeds {limit} byte limit for kind {kind}",
        )

    root = media_root()
    dest = resolve_media_path(root, safe_name)
    dest.write_bytes(data)

    optimized_for: OptimizedForResponse | None = None

    if kind == "video":
        result = await _optimize_video_upload(
            dest,
            target_width=target_width,
            target_height=target_height,
            target_fps=target_fps,
        )
        dest = result.path
        safe_name = dest.name
        data = dest.read_bytes()
        size = len(data)
        optimized_for = OptimizedForResponse(
            width=result.optimized_for.width,
            height=result.optimized_for.height,
            fps=result.optimized_for.fps,
        )

    if kind == "audio" and is_lossless_audio_filename(safe_name):
        result = await _optimize_audio_upload(dest)
        dest = result.path
        safe_name = dest.name
        data = dest.read_bytes()
        size = len(data)

    if kind == "image" and upload_context is not None:
        optimized_for = await _apply_image_upload_policy(
            dest,
            clip_type=upload_context[0],
            plugin_id=upload_context[1],
            field=field.strip() or "source",
            target_width=target_width,
            target_height=target_height,
            target_fps=target_fps,
        )

    await _write_upload_manifest(
        dest,
        upload_context=upload_context,
        kind=kind,
        optimized_for=optimized_for,
    )

    return _media_upload_response(request, dest, optimized_for=optimized_for)


@router.post("/ingest-url", response_model=MediaUploadResponse)
async def ingest_media_url(
    request: Request,
    body: IngestUrlRequest,
    kind: KindQuery = "image",
    clip_type: ClipTypeQuery = None,
    plugin_id: PluginIdQuery = None,
    field: FieldQuery = "source",
    target_width: TargetWidthQuery = None,
    target_height: TargetHeightQuery = None,
    target_fps: TargetFpsQuery = None,
) -> MediaUploadResponse:
    if kind not in _VALID_KINDS:
        raise HTTPException(status_code=400, detail=f"invalid kind: {kind}")

    upload_context = _validate_upload_context(clip_type, plugin_id)
    if upload_context is None:
        raise HTTPException(
            status_code=400,
            detail="clip_type and plugin_id are required for URL ingest",
        )

    limit = max_bytes_for_kind(kind)
    root = media_root()
    dest = allocate_ingest_path(root, body.url)

    if not dest.is_file():
        try:
            await asyncio.to_thread(fetch_url_to_path, body.url, dest, max_bytes=limit)
        except MediaFetchError as exc:
            dest.unlink(missing_ok=True)
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    optimized_for: OptimizedForResponse | None = None
    if kind == "image":
        optimized_for = await _apply_image_upload_policy(
            dest,
            clip_type=upload_context[0],
            plugin_id=upload_context[1],
            field=field.strip() or "source",
            target_width=target_width,
            target_height=target_height,
            target_fps=target_fps,
        )

    await _write_upload_manifest(
        dest,
        upload_context=upload_context,
        kind=kind,
        optimized_for=optimized_for,
    )

    return _media_upload_response(request, dest, optimized_for=optimized_for)


@router.get("/{filename}/upload-manifest", response_model=UploadManifestResponse)
async def get_upload_manifest(filename: str) -> UploadManifestResponse:
    try:
        safe_name = sanitize_upload_basename(filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    root = media_root()
    path = resolve_media_path(root, safe_name)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="not found")

    manifest = read_upload_manifest(path)
    if manifest is None:
        return UploadManifestResponse(optimized_for=None)

    raw = manifest.get("optimized_for")
    if not isinstance(raw, dict):
        return UploadManifestResponse(optimized_for=None)

    try:
        optimized_for = OptimizedForResponse(
            width=int(raw["width"]),
            height=int(raw["height"]),
            fps=float(raw["fps"]),
        )
    except (KeyError, TypeError, ValueError):
        return UploadManifestResponse(optimized_for=None)

    return UploadManifestResponse(optimized_for=optimized_for)


def _resolve_served_media_path(file_path: str) -> Path:
    """Resolve a URL path segment under ``media_root`` (flat or nested)."""
    rel = file_path.strip().replace("\\", "/").lstrip("/")
    if not rel:
        raise HTTPException(status_code=400, detail="invalid path")
    root = media_root()
    try:
        path = resolve_media_path(root, rel)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="not found")
    return path


def _resolve_existing_media_path(raw: str) -> Path:
    trimmed = raw.strip()
    if not trimmed:
        raise HTTPException(status_code=400, detail="source is required")

    root = media_root().resolve()
    candidate = Path(trimmed)
    if not candidate.is_absolute():
        try:
            safe_name = sanitize_upload_basename(trimmed)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        candidate = resolve_media_path(root, safe_name)

    resolved = candidate.resolve()
    if resolved != root and root not in resolved.parents:
        raise HTTPException(status_code=403, detail="source outside media root")
    if not resolved.is_file():
        raise HTTPException(status_code=404, detail="source not found")
    return resolved


def _boomerang_output_path(
    source: Path,
    *,
    start_offset: float,
    playback_rate: float,
    max_duration: float,
) -> Path:
    root = media_root()
    key = f"{source.resolve()}:{start_offset}:{playback_rate}:{max_duration}"
    digest = hashlib.sha256(key.encode()).hexdigest()[:12]
    safe_name = sanitize_upload_basename(f"{source.stem}.boomerang-{digest}.mp4")
    return resolve_media_path(root, safe_name)


@router.post("/video/boomerang", response_model=VideoBoomerangResponse)
async def create_video_boomerang(
    request: Request,
    body: VideoBoomerangRequest,
) -> VideoBoomerangResponse:
    if not video_ffmpeg_available():
        raise HTTPException(status_code=503, detail="ffmpeg not available for video boomerang")

    source = _resolve_existing_media_path(body.source)
    if is_boomerang_derivative_path(source):
        raise HTTPException(status_code=422, detail="source is already a boomerang derivative")
    output = _boomerang_output_path(
        source,
        start_offset=body.start_offset,
        playback_rate=body.playback_rate,
        max_duration=body.max_duration,
    )

    try:
        plan = await asyncio.to_thread(
            create_boomerang_video,
            source,
            output,
            start_offset=body.start_offset,
            playback_rate=body.playback_rate,
            max_duration=body.max_duration,
            target_fps=body.target_fps,
        )
    except VideoTranscodeError as exc:
        output.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    optimized_for: OptimizedForResponse | None = None
    if body.target_width is not None and body.target_height is not None:
        try:
            result = await asyncio.to_thread(
                optimize_video_upload,
                output,
                target_width=body.target_width,
                target_height=body.target_height,
                target_fps=body.target_fps,
            )
            output = result.path
            optimized_for = OptimizedForResponse(
                width=result.optimized_for.width,
                height=result.optimized_for.height,
                fps=result.optimized_for.fps,
            )
        except VideoTranscodeError as exc:
            output.unlink(missing_ok=True)
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    data = output.read_bytes()
    return VideoBoomerangResponse(
        path=str(output),
        filename=output.name,
        duration=plan.output_duration,
        size=len(data),
        url=f"{public_base_url(request)}/media/{output.name}",
        capped=plan.capped,
        optimized_for=optimized_for,
    )


def _reverse_output_path(
    source: Path,
    *,
    start_offset: float,
    playback_rate: float,
) -> Path:
    root = media_root()
    key = f"{source.resolve()}:{start_offset}:{playback_rate}:reverse"
    digest = hashlib.sha256(key.encode()).hexdigest()[:12]
    safe_name = sanitize_upload_basename(f"{source.stem}.reversed-{digest}.mp4")
    return resolve_media_path(root, safe_name)


@router.post("/video/reverse", response_model=VideoReverseResponse)
async def create_video_reverse(
    request: Request,
    body: VideoReverseRequest,
) -> VideoReverseResponse:
    if not video_ffmpeg_available():
        raise HTTPException(status_code=503, detail="ffmpeg not available for video reverse")

    source = _resolve_existing_media_path(body.source)
    output = _reverse_output_path(
        source,
        start_offset=body.start_offset,
        playback_rate=body.playback_rate,
    )

    try:
        plan = await asyncio.to_thread(
            create_reversed_video,
            source,
            output,
            start_offset=body.start_offset,
            playback_rate=body.playback_rate,
            target_fps=body.target_fps,
        )
    except VideoTranscodeError as exc:
        output.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    optimized_for: OptimizedForResponse | None = None
    if body.target_width is not None and body.target_height is not None:
        try:
            result = await asyncio.to_thread(
                optimize_video_upload,
                output,
                target_width=body.target_width,
                target_height=body.target_height,
                target_fps=body.target_fps,
            )
            output = result.path
            optimized_for = OptimizedForResponse(
                width=result.optimized_for.width,
                height=result.optimized_for.height,
                fps=result.optimized_for.fps,
            )
        except VideoTranscodeError as exc:
            output.unlink(missing_ok=True)
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    data = output.read_bytes()
    return VideoReverseResponse(
        path=str(output),
        filename=output.name,
        duration=plan.output_duration,
        size=len(data),
        url=f"{public_base_url(request)}/media/{output.name}",
        optimized_for=optimized_for,
    )


@router.get("/{file_path:path}")
async def get_media(file_path: str) -> FileResponse:
    path = _resolve_served_media_path(file_path)
    return FileResponse(path, filename=path.name)
