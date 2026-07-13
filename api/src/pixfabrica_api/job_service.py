"""Disk-backed render job queue and worker."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import shutil
import threading
import uuid
from collections import deque
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from pixfabrica_api.jobs_settings import (
    GRAPH_FILENAME,
    METADATA_FILENAME,
    VIDEO_FILENAME,
    jobs_root,
)
from pixfabrica_api.plugin_registry import ensure_plugins_registered
from pixfabrica_core.clips import RenderJob
from pixfabrica_core.errors import RenderError, RenderErrorCode
from pixfabrica_renderer.render import render_job

log = logging.getLogger("pixfabrica.api.jobs")

_TERMINAL = frozenset({"done", "cancelled", "failed", "interrupted"})
_ACTIVE = frozenset({"queued", "preparing", "rendering"})


class JobStatus(StrEnum):
    QUEUED = "queued"
    PREPARING = "preparing"
    RENDERING = "rendering"
    DONE = "done"
    CANCELLED = "cancelled"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class JobMetadata(BaseModel):
    id: str
    status: JobStatus = JobStatus.QUEUED
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    render_duration_ms: int | None = None
    render_parallelism_requested: Literal["single", "multi"] | None = None
    render_parallelism_effective: Literal["single", "multi"] | None = None
    title: str = "Untitled"
    width: int
    height: int
    fps: float
    duration_s: float
    error: str | None = None
    submitted_by: str | None = None
    executor: str = "local"


class JobRecord(JobMetadata):
    """API record — includes ephemeral progress for active jobs."""

    frame: int = 0
    total: int = 0
    percent: float = 0.0


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def _duration_ms(started_at: str | None, finished_at: str | None) -> int | None:
    start = _parse_iso(started_at)
    end = _parse_iso(finished_at)
    if start is None or end is None:
        return None
    return max(0, int((end - start).total_seconds() * 1000))


def _job_dir(job_id: str) -> Path:
    return jobs_root() / job_id


def _read_metadata(path: Path) -> JobMetadata:
    data = json.loads(path.read_text(encoding="utf-8"))
    return JobMetadata.model_validate(data)


def _write_metadata(path: Path, meta: JobMetadata) -> None:
    path.write_text(
        json.dumps(meta.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )


class JobService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._queue: deque[str] = deque()
        self._active_id: str | None = None
        self._cancel_events: dict[str, threading.Event] = {}
        self._live_progress: dict[str, dict[str, float | int]] = {}
        self._progress_queues: dict[str, list[asyncio.Queue[dict[str, Any]]]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._condition = threading.Condition(self._lock)
        self._worker_started = False

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self.recover_on_startup()
        if self._worker_started:
            return
        self._worker_started = True
        thread = threading.Thread(
            target=self._worker_loop, daemon=True, name="pixfabrica-job-worker"
        )
        thread.start()
        log.info("job worker started (jobs root: %s)", jobs_root())

    def recover_on_startup(self) -> None:
        root = jobs_root()
        for entry in root.iterdir():
            if not entry.is_dir():
                continue
            meta_path = entry / METADATA_FILENAME
            if not meta_path.is_file():
                continue
            try:
                meta = _read_metadata(meta_path)
            except Exception as exc:
                log.warning("skipping corrupt job metadata %s: %s", meta_path, exc)
                continue
            if meta.status.value in _ACTIVE:
                meta.status = JobStatus.INTERRUPTED
                meta.finished_at = _now_iso()
                meta.render_duration_ms = _duration_ms(meta.started_at, meta.finished_at)
                _write_metadata(meta_path, meta)
                log.info("marked job %s as interrupted after restart", meta.id)

    def list_jobs(self) -> list[JobMetadata]:
        root = jobs_root()
        rows: list[JobMetadata] = []
        for entry in root.iterdir():
            if not entry.is_dir():
                continue
            meta_path = entry / METADATA_FILENAME
            if not meta_path.is_file():
                continue
            try:
                rows.append(_read_metadata(meta_path))
            except Exception as exc:
                log.warning("skipping job %s: %s", entry.name, exc)
        rows.sort(key=lambda row: row.created_at, reverse=True)
        return rows

    def get_job(self, job_id: str) -> JobRecord | None:
        meta_path = _job_dir(job_id) / METADATA_FILENAME
        if not meta_path.is_file():
            return None
        meta = _read_metadata(meta_path)
        record = JobRecord.model_validate(meta.model_dump())
        live = self._live_progress.get(job_id)
        if live:
            record.frame = int(live.get("frame", 0))
            record.total = int(live.get("total", 0))
            record.percent = float(live.get("percent", 0.0))
        return record

    def video_path(self, job_id: str) -> Path | None:
        path = _job_dir(job_id) / VIDEO_FILENAME
        return path if path.is_file() else None

    def has_active_jobs(self) -> bool:
        return any(meta.status.value in _ACTIVE for meta in self.list_jobs())

    def create_job(self, graph_data: dict[str, Any]) -> str:
        job = RenderJob.model_validate(graph_data)
        job_id = str(uuid.uuid4())
        job_dir = _job_dir(job_id)
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / GRAPH_FILENAME).write_text(
            json.dumps(graph_data, indent=2) + "\n",
            encoding="utf-8",
        )
        meta = JobMetadata(
            id=job_id,
            status=JobStatus.QUEUED,
            created_at=_now_iso(),
            title=job.title or "Untitled",
            width=job.width,
            height=job.height,
            fps=job.fps,
            duration_s=job.duration,
            render_parallelism_requested=job.parallelism,
            submitted_by=None,
            executor="local",
        )
        _write_metadata(job_dir / METADATA_FILENAME, meta)
        cancel = threading.Event()
        self._cancel_events[job_id] = cancel
        with self._condition:
            self._queue.append(job_id)
            self._condition.notify()
        return job_id

    def cancel_job(self, job_id: str) -> None:
        meta_path = _job_dir(job_id) / METADATA_FILENAME
        if not meta_path.is_file():
            raise KeyError(job_id)
        meta = _read_metadata(meta_path)
        if meta.status.value in _TERMINAL:
            return

        if meta.status == JobStatus.QUEUED:
            with self._condition:
                _dequeue(self._queue, job_id)
            self._finalize(job_id, JobStatus.CANCELLED)
            return

        cancel = self._cancel_events.get(job_id)
        if cancel is not None:
            cancel.set()

    def delete_artifacts(self, job_id: str) -> bool:
        meta_path = _job_dir(job_id) / METADATA_FILENAME
        if not meta_path.is_file():
            return False
        meta = _read_metadata(meta_path)
        if meta.status in (JobStatus.PREPARING, JobStatus.RENDERING):
            raise ValueError("cannot delete active job")
        if meta.status == JobStatus.QUEUED:
            with self._condition:
                _dequeue(self._queue, job_id)
            cancel = self._cancel_events.pop(job_id, None)
            if cancel is not None:
                cancel.set()
        job_dir = _job_dir(job_id)
        if job_dir.is_dir():
            shutil.rmtree(job_dir)
        self._cancel_events.pop(job_id, None)
        self._live_progress.pop(job_id, None)
        self._progress_queues.pop(job_id, None)
        return True

    def subscribe_progress(self, job_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._progress_queues.setdefault(job_id, []).append(queue)

    def unsubscribe_progress(self, job_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        queues = self._progress_queues.get(job_id, [])
        if queue in queues:
            queues.remove(queue)

    def _worker_loop(self) -> None:
        while True:
            with self._condition:
                while not self._queue:
                    self._condition.wait()
                job_id = self._queue.popleft()
            try:
                self._run_job(job_id)
            except Exception as exc:
                log.error("unexpected worker failure for job %s: %s", job_id, exc, exc_info=True)

    def _run_job(self, job_id: str) -> None:
        self._active_id = job_id
        job_dir = _job_dir(job_id)
        meta_path = job_dir / METADATA_FILENAME
        output_path = job_dir / VIDEO_FILENAME
        cancel = self._cancel_events.setdefault(job_id, threading.Event())

        try:
            meta = _read_metadata(meta_path)
            if meta.status.value in _TERMINAL:
                return

            meta.status = JobStatus.PREPARING
            meta.started_at = _now_iso()
            _write_metadata(meta_path, meta)
            self._broadcast(job_id)

            graph_data = json.loads((job_dir / GRAPH_FILENAME).read_text(encoding="utf-8"))
            job = RenderJob.model_validate(graph_data)
            ensure_plugins_registered()

            async def _render() -> None:
                async for event in render_job(job, output_path, cancel=cancel):
                    if cancel.is_set() and event.stage != "cancelled":
                        continue
                    if event.stage == "prepare":
                        self._set_status(job_id, JobStatus.PREPARING)
                        self._emit_live(job_id, 0, event.total, 0.0)
                    elif event.stage == "render":
                        self._set_status(job_id, JobStatus.RENDERING)
                        if event.parallelism_effective is not None:
                            self._persist_parallelism_effective(job_id, event.parallelism_effective)
                        self._emit_live(job_id, event.frame, event.total, float(event.pct))
                    elif event.stage == "done":
                        self._finalize(job_id, JobStatus.DONE)
                    elif event.stage == "cancelled":
                        self._finalize(job_id, JobStatus.CANCELLED)

            asyncio.run(_render())

            meta = _read_metadata(meta_path)
            if meta.status == JobStatus.RENDERING and output_path.is_file():
                self._finalize(job_id, JobStatus.DONE)
        except RenderError as exc:
            if exc.code == RenderErrorCode.CANCELLED:
                self._finalize(job_id, JobStatus.CANCELLED)
            else:
                self._finalize(job_id, JobStatus.FAILED, error=exc.format("en"))
        except Exception as exc:
            log.error("render job %s failed: %s", job_id, exc, exc_info=True)
            self._finalize(job_id, JobStatus.FAILED, error=str(exc))
        finally:
            self._active_id = None
            self._cancel_events.pop(job_id, None)
            self._live_progress.pop(job_id, None)
            self._signal_ws_done(job_id)

    def _persist_parallelism_effective(
        self, job_id: str, effective: Literal["single", "multi"]
    ) -> None:
        meta_path = _job_dir(job_id) / METADATA_FILENAME
        if not meta_path.is_file():
            return
        meta = _read_metadata(meta_path)
        if meta.render_parallelism_effective is not None:
            return
        meta.render_parallelism_effective = effective
        _write_metadata(meta_path, meta)
        self._broadcast(job_id)

    def _set_status(self, job_id: str, status: JobStatus) -> None:
        meta_path = _job_dir(job_id) / METADATA_FILENAME
        if not meta_path.is_file():
            return
        meta = _read_metadata(meta_path)
        if meta.status == status:
            self._broadcast(job_id)
            return
        meta.status = status
        if status in (JobStatus.PREPARING, JobStatus.RENDERING) and meta.started_at is None:
            meta.started_at = _now_iso()
        _write_metadata(meta_path, meta)
        self._broadcast(job_id)

    def _finalize(
        self,
        job_id: str,
        status: JobStatus,
        *,
        error: str | None = None,
    ) -> None:
        meta_path = _job_dir(job_id) / METADATA_FILENAME
        if not meta_path.is_file():
            return
        meta = _read_metadata(meta_path)
        if meta.status.value in _TERMINAL:
            return
        meta.status = status
        meta.finished_at = _now_iso()
        meta.render_duration_ms = _duration_ms(meta.started_at, meta.finished_at)
        meta.error = error
        _write_metadata(meta_path, meta)
        if status != JobStatus.DONE:
            video = _job_dir(job_id) / VIDEO_FILENAME
            if video.is_file():
                with contextlib.suppress(OSError):
                    video.unlink()
        self._broadcast(job_id)

    def _emit_live(self, job_id: str, frame: int, total: int, percent: float) -> None:
        self._live_progress[job_id] = {"frame": frame, "total": total, "percent": percent}
        self._broadcast(job_id)

    def _broadcast(self, job_id: str) -> None:
        record = self.get_job(job_id)
        if record is None or self._loop is None:
            return
        payload = record.model_dump(mode="json")
        for queue in self._progress_queues.get(job_id, []):
            with contextlib.suppress(Exception):
                self._loop.call_soon_threadsafe(queue.put_nowait, payload)

    def _signal_ws_done(self, job_id: str) -> None:
        if self._loop is None:
            return
        for queue in self._progress_queues.get(job_id, []):
            with contextlib.suppress(Exception):
                self._loop.call_soon_threadsafe(queue.put_nowait, {"_done": True})


def _dequeue(queue: deque[str], job_id: str) -> None:
    with contextlib.suppress(ValueError):
        queue.remove(job_id)


job_service = JobService()
