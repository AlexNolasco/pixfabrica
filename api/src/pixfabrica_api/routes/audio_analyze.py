"""Background audio analysis for the web editor."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from pixfabrica_api.audio_analyze_service import audio_analyze_service
from pixfabrica_core.audio.analysis import AnalyzerKind

router = APIRouter(prefix="/audio/analyze", tags=["audio"])


class AnalyzeStartRequest(BaseModel):
    source: str = Field(description="Local path or http(s) URL")
    seek: float = Field(default=0.0, ge=0.0)
    duration: float | None = Field(default=None, ge=0.0)
    fps: float = Field(gt=0.0)
    beat_tightness: float = Field(default=200.0, ge=1.0, le=1000.0)
    analyzer: AnalyzerKind = Field(
        default=AnalyzerKind.STEM,
        description="StemAnalyzer — HTML5-style log spectrum + flux rhythm",
    )


class AnalyzeStartResponse(BaseModel):
    job_id: str
    status: Literal["queued", "running", "done", "failed", "cancelled"]
    progress: float


class AnalyzeStatusResponse(BaseModel):
    job_id: str
    status: Literal["queued", "running", "done", "failed", "cancelled"]
    progress: float
    error: str | None = None


def _status_payload(job_id: str) -> AnalyzeStatusResponse:
    job = audio_analyze_service.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return AnalyzeStatusResponse(
        job_id=job.job_id,
        status=job.status.value,  # type: ignore[arg-type]
        progress=job.progress,
        error=job.error,
    )


@router.post("", response_model=AnalyzeStartResponse)
async def start_audio_analyze(body: AnalyzeStartRequest) -> AnalyzeStartResponse:
    if not body.source.strip():
        raise HTTPException(status_code=400, detail="source is required")
    job = await audio_analyze_service.start(
        source=body.source.strip(),
        seek=body.seek,
        duration=body.duration,
        fps=body.fps,
        beat_tightness=body.beat_tightness,
        analyzer=body.analyzer,
    )
    return AnalyzeStartResponse(
        job_id=job.job_id,
        status=job.status.value,  # type: ignore[arg-type]
        progress=job.progress,
    )


@router.get("/{job_id}", response_model=AnalyzeStatusResponse)
async def get_audio_analyze_status(job_id: str) -> AnalyzeStatusResponse:
    return _status_payload(job_id)


@router.delete("/{job_id}", response_model=AnalyzeStatusResponse)
async def cancel_audio_analyze(job_id: str) -> AnalyzeStatusResponse:
    if not audio_analyze_service.cancel(job_id):
        raise HTTPException(status_code=404, detail="job not found")
    return _status_payload(job_id)
