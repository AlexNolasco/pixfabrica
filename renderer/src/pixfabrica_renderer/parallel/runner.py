"""ParallelFrameRunner — drives a WorkerPool, reorders results, writes ffmpeg.

Lifecycle:
  1. Caller constructs ProcessWorkerPool (or FakePool in tests) and runs
     await pool.start_staggered() to bring workers online.
  2. Caller iterates ``async for evt in runner.run(writer, total_frames, ...)``;
     evt is a ``RenderProgress`` whose frame counter advances on each in-order
     write to ffmpeg.
  3. Cancel: setting the supplied threading.Event makes the next-iteration
     check stop enqueuing and drain. Worker raise → RenderError + drain.
  4. Caller calls await pool.shutdown() in finally.

Backpressure: at most ``2 * pool.size`` frames are in flight (pending requests
+ heap entries) so memory stays bounded (~2N × width*height*4 bytes).

Reorder: results arrive arbitrary order; a min-heap waits until the next
expected frame number is at the top, then drains contiguously to ffmpeg.
"""

from __future__ import annotations

import heapq
import logging
import threading
from collections.abc import AsyncIterator

from pixfabrica_core.errors import RenderError, RenderErrorCode
from pixfabrica_core.progress import RenderProgress
from pixfabrica_renderer.parallel.protocol import (
    FrameDone,
    FrameError,
    FrameRequest,
    FrameSink,
    WorkerFatal,
    WorkerPool,
    WorkerReady,
)

log = logging.getLogger("pixfabrica.renderer.parallel.runner")


class ParallelFrameRunner:
    """Drives a worker pool to render ``total_frames`` and pipe to a VideoWriter
    in strict frame order. The pool is owned by the caller (so tests can inject
    FakePool); the runner just speaks the protocol.
    """

    def __init__(self, pool: WorkerPool, total_frames: int) -> None:
        if total_frames < 0:
            raise ValueError("total_frames must be non-negative")
        self._pool = pool
        self._total = total_frames

    async def run(
        self,
        writer: FrameSink,
        *,
        cancel: threading.Event | None = None,
    ) -> AsyncIterator[RenderProgress]:
        """Async generator yielding RenderProgress per frame *written* (in order)."""

        next_to_enqueue = 0
        next_to_write = 0
        in_flight = 0  # requests dispatched but not yet returned
        heap: list[tuple[int, bytes]] = []  # (frame_no, pixels)
        max_in_flight = max(2 * self._pool.size, 2)

        # Pre-fill the queue up to the backpressure cap.
        next_to_enqueue, in_flight = self._enqueue_more(
            next_to_enqueue, in_flight, max_in_flight, len(heap)
        )

        cancelled = False

        while next_to_write < self._total:
            if cancel is not None and cancel.is_set():
                cancelled = True
                break

            # Block briefly waiting for any worker message; the timeout lets
            # us re-check the cancel flag on idle workloads.
            msg = await self._pool.next_message(timeout=0.25)
            if msg is None:
                continue

            if isinstance(msg, WorkerReady):
                # Stale ready message (pool already started); ignore.
                continue

            if isinstance(msg, FrameError):
                raise RenderError(
                    RenderErrorCode.FFMPEG_FAILURE,
                    {
                        "detail": f"worker raised on frame {msg.frame_no}: {msg.exc_repr}",
                        "traceback": msg.traceback,
                        "frame": str(msg.frame_no),
                    },
                )

            if isinstance(msg, WorkerFatal):
                raise RenderError(
                    RenderErrorCode.FFMPEG_FAILURE,
                    {
                        "detail": f"worker {msg.worker_id} died: {msg.exc_repr}",
                        "traceback": msg.traceback,
                    },
                )

            if isinstance(msg, FrameDone):
                in_flight -= 1
                heapq.heappush(heap, (msg.frame_no, msg.pixels))
                # Drain any in-order frames at the top of the heap.
                while heap and heap[0][0] == next_to_write:
                    _, pixels = heapq.heappop(heap)
                    writer.write_frame_bytes(pixels)
                    next_to_write += 1
                    pct = int(next_to_write / self._total * 100) if self._total else 100
                    yield RenderProgress(
                        stage="render", frame=next_to_write, total=self._total, pct=pct
                    )
                # Refill request queue up to the cap.
                next_to_enqueue, in_flight = self._enqueue_more(
                    next_to_enqueue, in_flight, max_in_flight, len(heap)
                )
                continue

            log.warning("runner got unexpected message type %r", type(msg).__name__)

        if not cancelled:
            # Workers block on result_q.put when the pipe fills; keep draining until
            # every dispatched frame has returned so shutdown does not wait on stragglers.
            while in_flight > 0:
                msg = await self._pool.next_message(timeout=30.0)
                if msg is None:
                    log.warning(
                        "timed out draining parallel FrameDone (in_flight=%d); "
                        "workers may need SIGTERM during pool shutdown",
                        in_flight,
                    )
                    break
                if isinstance(msg, WorkerReady):
                    continue
                if isinstance(msg, FrameError):
                    raise RenderError(
                        RenderErrorCode.FFMPEG_FAILURE,
                        {
                            "detail": f"worker raised on frame {msg.frame_no}: {msg.exc_repr}",
                            "traceback": msg.traceback,
                            "frame": str(msg.frame_no),
                        },
                    )
                if isinstance(msg, WorkerFatal):
                    raise RenderError(
                        RenderErrorCode.FFMPEG_FAILURE,
                        {
                            "detail": f"worker {msg.worker_id} died: {msg.exc_repr}",
                            "traceback": msg.traceback,
                        },
                    )
                if isinstance(msg, FrameDone):
                    in_flight -= 1
                    continue
                log.warning("runner got unexpected message type %r", type(msg).__name__)

        if cancelled:
            yield RenderProgress(
                stage="cancelled",
                frame=next_to_write,
                total=self._total,
                pct=int(next_to_write / self._total * 100) if self._total else 0,
            )
            raise RenderError(RenderErrorCode.CANCELLED)

    def _enqueue_more(
        self,
        next_to_enqueue: int,
        in_flight: int,
        max_in_flight: int,
        heap_size: int,
    ) -> tuple[int, int]:
        """Push as many FrameRequests as backpressure allows."""
        budget = max_in_flight - (in_flight + heap_size)
        to_send: list[FrameRequest] = []
        while budget > 0 and next_to_enqueue < self._total:
            to_send.append(FrameRequest(frame_no=next_to_enqueue))
            next_to_enqueue += 1
            in_flight += 1
            budget -= 1
        if to_send:
            self._pool.submit(to_send)
        return next_to_enqueue, in_flight
