"""Render job endpoints."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel

from pixfabrica_api.gl_policy import validate_graph_gl_policy
from pixfabrica_api.job_discord_export import (
    DiscordExportTooLargeError,
    discord_export_filename,
    export_discord_video,
)
from pixfabrica_api.job_service import JobRecord, JobStatus, job_service
from pixfabrica_api.license_policy import validate_graph_license_policy
from pixfabrica_api.project_limits import validate_graph_policy
from pixfabrica_api.video_transcode import VideoTranscodeError, ffmpeg_available

log = logging.getLogger("pixfabrica.api.jobs")

router = APIRouter(prefix="/jobs", tags=["jobs"])

_TERMINAL = frozenset(
    {
        JobStatus.DONE,
        JobStatus.CANCELLED,
        JobStatus.FAILED,
        JobStatus.INTERRUPTED,
    }
)
_ACTIVE = frozenset(
    {
        JobStatus.QUEUED,
        JobStatus.PREPARING,
        JobStatus.RENDERING,
    }
)


class CreateJobRequest(BaseModel):
    graph: dict[str, Any]


class CreateJobResponse(BaseModel):
    job_id: str


class CancelJobResponse(BaseModel):
    status: str


class DeleteArtifactsResponse(BaseModel):
    status: str


@router.get("", response_model=list[JobRecord])
async def list_jobs() -> list[JobRecord]:
    return [JobRecord.model_validate(row.model_dump()) for row in job_service.list_jobs()]


@router.post("", response_model=CreateJobResponse)
async def create_job(body: CreateJobRequest) -> CreateJobResponse:
    validate_graph_policy(body.graph)
    validate_graph_gl_policy(body.graph)
    validate_graph_license_policy(body.graph)
    job_id = job_service.create_job(body.graph)
    return CreateJobResponse(job_id=job_id)


@router.get("/{job_id}", response_model=JobRecord)
async def get_job(job_id: str) -> JobRecord:
    record = job_service.get_job(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return record


@router.delete("/{job_id}", response_model=CancelJobResponse)
async def cancel_job(job_id: str) -> CancelJobResponse:
    record = job_service.get_job(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if record.status in _TERMINAL:
        raise HTTPException(status_code=409, detail=f"Job already {record.status.value}")
    job_service.cancel_job(job_id)
    return CancelJobResponse(status="cancelled")


@router.delete("/{job_id}/artifacts", response_model=DeleteArtifactsResponse)
async def delete_job_artifacts(job_id: str) -> DeleteArtifactsResponse:
    record = job_service.get_job(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if record.status in (JobStatus.PREPARING, JobStatus.RENDERING):
        raise HTTPException(status_code=409, detail="Cancel the job before removing it")
    try:
        deleted = job_service.delete_artifacts(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Job not found")
    return DeleteArtifactsResponse(status="removed")


def _require_done_job_video(job_id: str) -> tuple[JobRecord, Path]:
    record = job_service.get_job(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if record.status != JobStatus.DONE:
        raise HTTPException(status_code=404, detail="Video not available")
    path = job_service.video_path(job_id)
    if path is None:
        raise HTTPException(status_code=404, detail="Video not found")
    return record, Path(path)


@router.get("/{job_id}/video")
async def get_job_video(
    job_id: str,
    disposition: str = Query(default="inline", pattern="^(inline|attachment)$"),
) -> FileResponse:
    record, path = _require_done_job_video(job_id)
    filename = f"{record.title or job_id}.mp4".replace("/", "-")
    return FileResponse(
        path,
        media_type="video/mp4",
        filename=filename,
        content_disposition_type=disposition,
    )


@router.get("/{job_id}/video/discord")
async def get_job_video_discord(
    job_id: str,
    background_tasks: BackgroundTasks,
    max_mb: int = Query(default=8),
) -> FileResponse:
    if max_mb not in (8, 50):
        raise HTTPException(status_code=422, detail="max_mb must be 8 or 50")
    if not ffmpeg_available():
        raise HTTPException(status_code=503, detail="ffmpeg/ffprobe not available")
    record, path = _require_done_job_video(job_id)
    try:
        export_path = export_discord_video(path, max_mb=max_mb)
    except DiscordExportTooLargeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except VideoTranscodeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    filename = discord_export_filename(record.title or job_id, job_id, max_mb=max_mb)
    background_tasks.add_task(export_path.unlink, True)
    return FileResponse(
        export_path,
        media_type="video/mp4",
        filename=filename,
        content_disposition_type="attachment",
    )


@router.websocket("/{job_id}/progress")
async def job_progress_ws(job_id: str, websocket: WebSocket) -> None:
    if job_service.get_job(job_id) is None:
        await websocket.close(code=4004)
        return

    await websocket.accept()
    log.info("progress WS connected for job %s", job_id)

    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    job_service.subscribe_progress(job_id, queue)

    try:
        record = job_service.get_job(job_id)
        assert record is not None
        await websocket.send_text(record.model_dump_json())

        if record.status in _TERMINAL:
            return

        while True:
            update = await queue.get()
            if update.get("_done"):
                break
            record = job_service.get_job(job_id)
            if record is None:
                break
            await websocket.send_text(record.model_dump_json())
            if record.status in _TERMINAL:
                break

    except WebSocketDisconnect:
        log.info("progress WS disconnected for job %s", job_id)
    finally:
        job_service.unsubscribe_progress(job_id, queue)
