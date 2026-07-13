"""ProcessWorkerPool — real multiprocessing implementation of WorkerPool.

Uses ``spawn`` everywhere (Windows-friendly default) and routes worker output
through two queues. The pool stays cheap to construct: workers come up via
start_staggered() so a cold cache only stalls one worker at a time.
"""

from __future__ import annotations

import asyncio
import logging
import multiprocessing as mp
import queue as stdlib_queue
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from pixfabrica_renderer.parallel.protocol import (
    FrameRequest,
    Shutdown,
    WorkerFatal,
    WorkerMessage,
    WorkerReady,
)
from pixfabrica_renderer.parallel.worker import worker_main

log = logging.getLogger("pixfabrica.renderer.parallel.pool")

# Workers do their own multi-threaded heavy lifting (Skia, numpy, ffmpeg-pipe).
# A single shared ThreadPoolExecutor turns blocking queue.get() calls into
# awaitables for the runner without spawning a thread per call.
_QUEUE_DRAIN_THREADS = 1


class ProcessWorkerPool:
    """Owns N worker processes; exposes WorkerPool surface for ParallelFrameRunner."""

    def __init__(
        self,
        *,
        size: int,
        job_payload: dict[str, Any],
        width: int,
        height: int,
        fps: float,
        locale: str,
        audio_timeline_payload: dict[str, list[dict[str, Any]]],
        plugins_dir: str | None = None,
    ) -> None:
        if size < 1:
            raise ValueError("pool size must be >= 1")
        self._size = size
        self._mp_ctx = mp.get_context("spawn")
        self._request_q: Any = self._mp_ctx.Queue()
        self._result_q: Any = self._mp_ctx.Queue()
        self._processes: list[Any] = []
        self._executor = ThreadPoolExecutor(max_workers=_QUEUE_DRAIN_THREADS)
        self._init_args = dict(
            job_payload=job_payload,
            width=width,
            height=height,
            fps=fps,
            locale=locale,
            audio_timeline_payload=audio_timeline_payload,
            plugins_dir=plugins_dir,
        )
        self._shutdown_complete = False

    @property
    def size(self) -> int:
        return self._size

    async def start_staggered(self) -> None:
        """Spawn worker 0 alone (warms on-disk caches), then 1..N-1 in parallel."""
        loop = asyncio.get_event_loop()
        # Bring worker 0 up alone.
        self._spawn_one(0)
        log.info("waiting for worker 0 (cache-warm pass)")
        await self._await_ready(0)

        # Spawn the rest concurrently.
        for wid in range(1, self._size):
            self._spawn_one(wid)
        log.info("waiting for workers 1..%d to ready", self._size - 1)
        ready_tasks = [loop.create_task(self._await_ready(wid)) for wid in range(1, self._size)]
        if ready_tasks:
            await asyncio.gather(*ready_tasks)
        log.info("all %d worker(s) ready", self._size)

    def _spawn_one(self, worker_id: int) -> None:
        proc = self._mp_ctx.Process(
            target=worker_main,
            args=(worker_id, self._request_q, self._result_q),
            kwargs=self._init_args,
            name=f"pixfabrica-worker-{worker_id}",
            daemon=True,  # backstop: parent crash does not orphan workers
        )
        proc.start()
        self._processes.append(proc)

    async def _await_ready(self, worker_id: int) -> None:
        """Pull from result_q until the matching WorkerReady (or fatal) arrives.

        Re-queues unrelated messages (other workers' WorkerReady) so they can be
        consumed by the next ``_await_ready`` call.
        """
        loop = asyncio.get_event_loop()
        while True:
            msg = await loop.run_in_executor(self._executor, self._result_q.get)
            if isinstance(msg, WorkerReady):
                if msg.worker_id == worker_id:
                    return
                # Belongs to another worker — push back so its waiter sees it.
                self._result_q.put(msg)
            elif isinstance(msg, WorkerFatal):
                raise RuntimeError(
                    f"worker {msg.worker_id} died during prepare: {msg.exc_repr}\n{msg.traceback}"
                )
            else:
                # Stray non-ready message (shouldn't happen pre-start); preserve it.
                self._result_q.put(msg)

    def submit(self, requests: Iterable[FrameRequest]) -> None:
        for req in requests:
            self._request_q.put(req)

    async def next_message(self, timeout: float | None = None) -> WorkerMessage | None:
        loop = asyncio.get_event_loop()

        def _get() -> WorkerMessage | None:
            try:
                return self._result_q.get(timeout=timeout)
            except stdlib_queue.Empty:
                return None

        return await loop.run_in_executor(self._executor, _get)

    async def shutdown(self, *, terminate_after: float = 15.0) -> None:
        if self._shutdown_complete:
            return
        self._shutdown_complete = True
        for _ in range(self._size):
            self._request_q.put(Shutdown())

        loop = asyncio.get_event_loop()

        def _join_one(proc: Any) -> None:
            proc.join(timeout=terminate_after)
            if proc.is_alive():
                log.warning("worker %s did not exit cleanly; terminating", proc.name)
                proc.terminate()
                proc.join(timeout=2.0)

        join_workers = max(1, self._size)
        join_exec = ThreadPoolExecutor(max_workers=join_workers)
        try:
            await asyncio.gather(
                *[loop.run_in_executor(join_exec, _join_one, p) for p in self._processes]
            )
        finally:
            join_exec.shutdown(wait=True)

        self._executor.shutdown(wait=False, cancel_futures=True)
        # Drain queues so background feeder threads exit promptly.
        for q in (self._request_q, self._result_q):
            try:
                q.close()
                q.join_thread()
            except Exception:  # noqa: BLE001 — best-effort cleanup
                pass
