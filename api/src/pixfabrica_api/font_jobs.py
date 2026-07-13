"""In-memory font install job tracking."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from enum import StrEnum

from pixfabrica_core.fonts import (
    clear_skia_font_cache,
    install_font_upload,
    rebuild_font_catalog,
)
from pixfabrica_core.fonts.manifest import FontManifestError

log = logging.getLogger("pixfabrica.api.font_jobs")


class FontJobStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class FontJob:
    id: str
    status: FontJobStatus
    families: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


_jobs: dict[str, FontJob] = {}


def get_font_job(job_id: str) -> FontJob | None:
    return _jobs.get(job_id)


def create_font_job() -> FontJob:
    job_id = str(uuid.uuid4())
    job = FontJob(id=job_id, status=FontJobStatus.PENDING)
    _jobs[job_id] = job
    return job


def run_font_install_job(job_id: str, data: bytes, filename: str) -> None:
    job = _jobs.get(job_id)
    if job is None:
        return

    try:
        result = install_font_upload(data, filename)
        if not result.ok:
            detail = "; ".join(result.warnings) or "no valid font files found"
            job.status = FontJobStatus.FAILED
            job.error = detail
            job.warnings = list(result.warnings)
            return

        try:
            rebuild_font_catalog()
        except FontManifestError as exc:
            job.status = FontJobStatus.FAILED
            job.error = str(exc)
            return
        clear_skia_font_cache()

        job.status = FontJobStatus.COMPLETED
        job.families = list(result.families)
        job.warnings = list(result.warnings)
    except Exception as exc:
        log.exception("font install job %s failed", job_id)
        job.status = FontJobStatus.FAILED
        job.error = str(exc)


def reset_font_jobs_for_tests() -> None:
    _jobs.clear()
