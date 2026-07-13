"""Background audio analysis jobs for the editor (decoupled from preview WebSocket)."""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from pixfabrica_api.server_config import DEFAULT_LOCALE
from pixfabrica_core.audio.analysis import AnalysisCancelledError, AnalyzerKind, _resolve_source
from pixfabrica_core.audio.cache import analyze_to_cache, timeline_cache_path_for_file
from pixfabrica_core.clips import JobInfo, PrepareContext
from pixfabrica_core.theme.color import ColorPalette
from pixfabrica_core.theme.typography import FontPalette

log = logging.getLogger("pixfabrica.api.audio_analyze")

_MAX_CONCURRENT = 2


class AnalyzeJobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class AnalyzeJobParams:
    source: str
    seek: float
    duration: float | None
    fps: float
    beat_tightness: float
    analyzer: AnalyzerKind


@dataclass
class AnalyzeJob:
    job_id: str
    params: AnalyzeJobParams
    status: AnalyzeJobStatus = AnalyzeJobStatus.QUEUED
    progress: float = 0.0
    error: str | None = None
    cancel: threading.Event = field(default_factory=threading.Event)


class AudioAnalyzeService:
    def __init__(self) -> None:
        self._jobs: dict[str, AnalyzeJob] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(
            max_workers=_MAX_CONCURRENT,
            thread_name_prefix="audio-analyze",
        )

    def get(self, job_id: str) -> AnalyzeJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            return False
        job.cancel.set()
        if job.status in (AnalyzeJobStatus.QUEUED, AnalyzeJobStatus.RUNNING):
            job.status = AnalyzeJobStatus.CANCELLED
        return True

    async def start(
        self,
        *,
        source: str,
        seek: float,
        duration: float | None,
        fps: float,
        beat_tightness: float,
        analyzer: AnalyzerKind = AnalyzerKind.STEM,
    ) -> AnalyzeJob:
        job_id = uuid.uuid4().hex
        params = AnalyzeJobParams(
            source=source,
            seek=seek,
            duration=duration,
            fps=fps,
            beat_tightness=beat_tightness,
            analyzer=analyzer,
        )
        job = AnalyzeJob(job_id=job_id, params=params)
        with self._lock:
            self._jobs[job_id] = job

        ji = JobInfo(
            title="analyze",
            description="",
            width=1280,
            height=720,
            fps=fps,
            duration=float(duration) if duration is not None else 60.0,
            colors=ColorPalette(),
            typography=FontPalette(),
            locale=DEFAULT_LOCALE,
        )
        ctx = PrepareContext.from_env(ji)
        local_path = await _resolve_source(source, ctx)

        cache_file = timeline_cache_path_for_file(
            ctx.cache_dir,
            local_path,
            seek,
            duration,
            fps,
            beat_tightness,
        )
        if cache_file.exists():
            job.status = AnalyzeJobStatus.DONE
            job.progress = 1.0
            return job

        loop = asyncio.get_running_loop()
        loop.run_in_executor(
            self._executor,
            self._run_job,
            job,
            ctx.cache_dir,
            local_path,
        )
        return job

    def _run_job(self, job: AnalyzeJob, cache_dir: Path, local_path: Path) -> None:
        seek = job.params.seek
        duration_f = job.params.duration
        fps = job.params.fps
        beat_tightness = job.params.beat_tightness

        with self._lock:
            if job.status == AnalyzeJobStatus.CANCELLED:
                return
            job.status = AnalyzeJobStatus.RUNNING

        try:

            def on_progress(p: float) -> None:
                job.progress = max(0.0, min(1.0, float(p)))

            analyze_to_cache(
                cache_dir=cache_dir,
                local_path=local_path,
                seek=seek,
                duration=duration_f,
                fps=fps,
                beat_tightness=beat_tightness,
                on_progress=on_progress,
                cancel=job.cancel,
            )
            with self._lock:
                if job.cancel.is_set():
                    job.status = AnalyzeJobStatus.CANCELLED
                else:
                    job.status = AnalyzeJobStatus.DONE
                    job.progress = 1.0
        except AnalysisCancelledError:
            with self._lock:
                job.status = AnalyzeJobStatus.CANCELLED
        except Exception as exc:
            log.exception("audio analyze job %s failed", job.job_id)
            with self._lock:
                if job.cancel.is_set():
                    job.status = AnalyzeJobStatus.CANCELLED
                else:
                    job.status = AnalyzeJobStatus.FAILED
                    job.error = str(exc)


audio_analyze_service = AudioAnalyzeService()
