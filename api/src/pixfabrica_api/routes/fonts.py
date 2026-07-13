"""Font catalog, static previews, and user font installation."""

from __future__ import annotations

import logging
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from pixfabrica_api.font_jobs import (
    create_font_job,
    get_font_job,
    run_font_install_job,
)
from pixfabrica_core.fonts import (
    MAX_FONT_UPLOAD_BYTES,
    get_font_catalog,
    resolve_font_file,
)
from pixfabrica_core.fonts.manifest import FontManifestError

log = logging.getLogger("pixfabrica.api.fonts")

router = APIRouter(tags=["fonts"])

FontUpload = Annotated[UploadFile, File()]


class FontWeightResponse(BaseModel):
    value: int
    preview_url: str


class FontFamilyResponse(BaseModel):
    id: str
    family: str
    label: str
    category: Literal["sans", "mono"]
    weights: list[FontWeightResponse]


class FontJobCreateResponse(BaseModel):
    job_id: str
    status: Literal["pending"] = "pending"


class FontJobResponse(BaseModel):
    job_id: str
    status: Literal["pending", "completed", "failed"]
    families: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None


@router.get("/fonts", response_model=list[FontFamilyResponse])
async def list_fonts() -> list[FontFamilyResponse]:
    try:
        catalog = get_font_catalog()
    except FontManifestError as exc:
        log.warning("font catalog unavailable: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return [
        FontFamilyResponse(
            id=entry.id,
            family=entry.family,
            label=entry.label,
            category=entry.category,
            weights=[
                FontWeightResponse(value=w.value, preview_url=w.preview_url) for w in entry.weights
            ],
        )
        for entry in catalog
    ]


@router.post("/fonts", response_model=FontJobCreateResponse)
async def upload_font(file: FontUpload, background_tasks: BackgroundTasks) -> FontJobCreateResponse:
    original = file.filename or "upload.ttf"
    suffix = original.rsplit(".", 1)[-1].lower() if "." in original else ""
    if suffix not in {"ttf", "otf", "zip"}:
        raise HTTPException(status_code=400, detail="expected .ttf, .otf, or .zip upload")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty upload")
    if len(data) > MAX_FONT_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"file exceeds {MAX_FONT_UPLOAD_BYTES} byte limit",
        )

    job = create_font_job()
    background_tasks.add_task(run_font_install_job, job.id, data, original)
    return FontJobCreateResponse(job_id=job.id)


@router.get("/fonts/jobs/{job_id}", response_model=FontJobResponse)
async def get_font_install_job(job_id: str) -> FontJobResponse:
    job = get_font_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="font install job not found")
    return FontJobResponse(
        job_id=job.id,
        status=job.status.value,
        families=job.families,
        warnings=job.warnings,
        error=job.error,
    )


@router.get("/fonts/files/{filename}")
async def get_font_file(filename: str) -> FileResponse:
    path = resolve_font_file(filename)
    if path is None:
        raise HTTPException(status_code=404, detail="Font file not found")

    media = "font/woff2" if path.suffix.lower() == ".woff2" else "font/ttf"
    if path.suffix.lower() == ".otf":
        media = "font/otf"
    return FileResponse(path, media_type=media)
