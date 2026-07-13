"""ParallelFrameRunner unit tests with an in-process FakePool.

Covers the runner's logic without spawning real subprocesses:
  * In-order writes despite out-of-order completion
  * Backpressure cap at 2 * pool.size in flight
  * Cancellation via threading.Event
  * Frame error → RenderError(FFMPEG_FAILURE) with traceback in context
  * Worker fatal → RenderError(FFMPEG_FAILURE) with worker_id in detail
  * Progress events monotonically equal frame written count
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
from collections import deque
from collections.abc import Callable, Iterable

import pytest

from pixfabrica_core.errors import RenderError, RenderErrorCode
from pixfabrica_renderer.parallel import (
    FrameDone,
    FrameError,
    FrameRequest,
    ParallelFrameRunner,
    Shutdown,
    WorkerFatal,
    WorkerMessage,
    WorkerPool,
)

# ── Fakes ─────────────────────────────────────────────────────────────────────


class FakeWriter:
    """Captures every frame the runner pipes; mimics VideoWriter's bytes API."""

    def __init__(self) -> None:
        self.frames_written: list[bytes] = []

    def write_frame_bytes(self, pixels: bytes | memoryview) -> None:
        self.frames_written.append(bytes(pixels))


class FakePool:
    """In-process WorkerPool driven by a scripted scheduling function.

    ``scheduler`` receives the list of pending FrameRequests and yields
    WorkerMessages in whatever order the test wants. The pool guarantees
    backpressure behavior is observable: it tracks max_in_flight as a
    side effect for tests to assert on.
    """

    def __init__(
        self,
        size: int,
        scheduler: Callable[[deque[int]], list[WorkerMessage]],
    ) -> None:
        self._size = size
        self._scheduler = scheduler
        self._pending: deque[int] = deque()
        self._outbox: deque[WorkerMessage] = deque()
        self.max_in_flight_seen = 0
        self.shutdown_called = False

    @property
    def size(self) -> int:
        return self._size

    async def start_staggered(self) -> None:
        return

    def submit(self, requests: Iterable[FrameRequest]) -> None:
        for req in requests:
            self._pending.append(req.frame_no)
        if len(self._pending) > self.max_in_flight_seen:
            self.max_in_flight_seen = len(self._pending)

    async def next_message(self, timeout: float | None = None) -> WorkerMessage | None:
        if not self._outbox:
            produced = self._scheduler(self._pending)
            for msg in produced:
                self._outbox.append(msg)
        if self._outbox:
            msg = self._outbox.popleft()
            if isinstance(msg, FrameDone):
                # Mirror real worker: frame leaves pending when it completes.
                with contextlib.suppress(ValueError):
                    self._pending.remove(msg.frame_no)
            return msg
        await asyncio.sleep(0)
        return None

    async def shutdown(self, *, terminate_after: float = 5.0) -> None:
        self.shutdown_called = True


def _frame_bytes(n: int) -> bytes:
    """Deterministic per-frame payload so tests can verify ordering exactly."""
    return f"frame-{n}".encode()


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_runner_writes_frames_in_order_despite_oos_completion() -> None:
    """Workers complete frames out-of-order; runner must reorder."""

    def scheduler(pending: deque[int]) -> list[WorkerMessage]:
        if not pending:
            return []
        ordered = sorted(pending, reverse=True)
        msgs: list[WorkerMessage] = [FrameDone(frame_no=n, pixels=_frame_bytes(n)) for n in ordered]
        return msgs

    pool = FakePool(size=2, scheduler=scheduler)
    runner = ParallelFrameRunner(pool=pool, total_frames=10)
    writer = FakeWriter()

    progress_events = []
    async for evt in runner.run(writer):
        progress_events.append(evt)

    assert writer.frames_written == [_frame_bytes(i) for i in range(10)]
    assert [e.frame for e in progress_events] == list(range(1, 11))
    assert all(e.stage == "render" for e in progress_events)


@pytest.mark.asyncio
async def test_runner_respects_backpressure_cap() -> None:
    """In-flight frames must never exceed 2 * pool.size."""
    pool_size = 3

    def scheduler(pending: deque[int]) -> list[WorkerMessage]:
        # Complete one frame at a time, lowest-first.
        if not pending:
            return []
        n = min(pending)
        return [FrameDone(frame_no=n, pixels=_frame_bytes(n))]

    pool = FakePool(size=pool_size, scheduler=scheduler)
    runner = ParallelFrameRunner(pool=pool, total_frames=20)
    writer = FakeWriter()

    async for _ in runner.run(writer):
        pass

    # Cap is 2 * pool_size; we never see more than that pending at once.
    assert pool.max_in_flight_seen <= 2 * pool_size
    assert len(writer.frames_written) == 20


@pytest.mark.asyncio
async def test_runner_cancels_via_event() -> None:
    """Setting cancel mid-render → CANCELLED RenderError, no further writes."""
    cancel_after = 5
    cancel = threading.Event()

    def scheduler(pending: deque[int]) -> list[WorkerMessage]:
        if not pending:
            return []
        n = min(pending)
        if n == cancel_after:
            cancel.set()
        return [FrameDone(frame_no=n, pixels=_frame_bytes(n))]

    pool = FakePool(size=2, scheduler=scheduler)
    runner = ParallelFrameRunner(pool=pool, total_frames=50)
    writer = FakeWriter()

    with pytest.raises(RenderError) as exc_info:
        async for _ in runner.run(writer, cancel=cancel):
            pass

    assert exc_info.value.code == RenderErrorCode.CANCELLED
    # Some frames near the cancel point made it through.
    assert len(writer.frames_written) >= cancel_after
    assert len(writer.frames_written) < 50


@pytest.mark.asyncio
async def test_runner_propagates_frame_error() -> None:
    """A worker FrameError → RenderError with traceback in context."""

    def scheduler(pending: deque[int]) -> list[WorkerMessage]:
        if not pending:
            return []
        n = min(pending)
        if n == 3:
            return [
                FrameError(
                    frame_no=3,
                    exc_repr="ValueError('boom')",
                    traceback="Traceback ...\nValueError: boom",
                )
            ]
        return [FrameDone(frame_no=n, pixels=_frame_bytes(n))]

    pool = FakePool(size=2, scheduler=scheduler)
    runner = ParallelFrameRunner(pool=pool, total_frames=10)
    writer = FakeWriter()

    with pytest.raises(RenderError) as exc_info:
        async for _ in runner.run(writer):
            pass

    assert exc_info.value.code == RenderErrorCode.FFMPEG_FAILURE
    assert "boom" in exc_info.value.context["detail"]
    assert exc_info.value.context["frame"] == "3"
    assert "Traceback" in exc_info.value.context["traceback"]


@pytest.mark.asyncio
async def test_runner_propagates_worker_fatal() -> None:
    """A WorkerFatal (e.g. crash during prepare) → RenderError mid-render."""

    def scheduler(pending: deque[int]) -> list[WorkerMessage]:
        if not pending:
            return []
        n = min(pending)
        if n >= 2:
            return [
                WorkerFatal(
                    worker_id=1,
                    exc_repr="OSError('GPU lost')",
                    traceback="Traceback ...\nOSError: GPU lost",
                )
            ]
        return [FrameDone(frame_no=n, pixels=_frame_bytes(n))]

    pool = FakePool(size=2, scheduler=scheduler)
    runner = ParallelFrameRunner(pool=pool, total_frames=10)
    writer = FakeWriter()

    with pytest.raises(RenderError) as exc_info:
        async for _ in runner.run(writer):
            pass

    assert exc_info.value.code == RenderErrorCode.FFMPEG_FAILURE
    assert "worker 1" in exc_info.value.context["detail"]
    assert "GPU lost" in exc_info.value.context["detail"]


@pytest.mark.asyncio
async def test_runner_zero_frames_yields_nothing() -> None:
    """Edge case: total_frames=0 finishes immediately, no errors."""
    pool = FakePool(size=2, scheduler=lambda pending: [])
    runner = ParallelFrameRunner(pool=pool, total_frames=0)
    writer = FakeWriter()

    events = [evt async for evt in runner.run(writer)]
    assert events == []
    assert writer.frames_written == []


@pytest.mark.asyncio
async def test_runner_progress_is_monotonic() -> None:
    """Frame counter only ever increases by 1 per render event."""

    def scheduler(pending: deque[int]) -> list[WorkerMessage]:
        if not pending:
            return []
        # Mix of orderings to stress reorder logic.
        n = max(pending) if len(pending) > 3 else min(pending)
        return [FrameDone(frame_no=n, pixels=_frame_bytes(n))]

    pool = FakePool(size=4, scheduler=scheduler)
    runner = ParallelFrameRunner(pool=pool, total_frames=15)
    writer = FakeWriter()

    frames = []
    async for evt in runner.run(writer):
        frames.append(evt.frame)

    assert frames == list(range(1, 16))


def test_pool_protocol_subclass_check() -> None:
    """FakePool implements WorkerPool — runtime structural check."""
    pool = FakePool(size=1, scheduler=lambda pending: [])
    assert isinstance(pool, WorkerPool)


@pytest.mark.asyncio
async def test_protocol_message_types_are_distinct() -> None:
    """Smoke check that the WorkerMessage union covers the wire."""
    assert isinstance(FrameDone(frame_no=0, pixels=b""), WorkerMessage)  # type: ignore[arg-type]
    assert isinstance(
        FrameError(frame_no=0, exc_repr="", traceback=""),
        WorkerMessage,  # type: ignore[arg-type]
    )
    assert isinstance(
        WorkerFatal(worker_id=0, exc_repr="", traceback=""),
        WorkerMessage,  # type: ignore[arg-type]
    )
    # Sanity: parent → worker types live alongside but aren't in WorkerMessage.
    _ = FrameRequest(frame_no=0)
    _ = Shutdown()
