"""IPC message types and the WorkerPool interface.

Why a Protocol: ParallelFrameRunner depends on a small abstract pool, not on
multiprocessing directly. Tests inject an in-process FakePool to exercise
reorder/backpressure/cancel/error paths without spawning real subprocesses.

Wire shape (parent ↔ worker):
    parent → worker:   FrameRequest(frame_no) | Shutdown()
    worker → parent:   WorkerReady | FrameDone(frame_no, pixels) |
                       FrameError(frame_no, exc, traceback) |
                       WorkerFatal(exc, traceback)
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

# ── Parent → Worker ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FrameRequest:
    frame_no: int


@dataclass(frozen=True)
class Shutdown:
    pass


# ── Worker → Parent ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class WorkerReady:
    worker_id: int


@dataclass(frozen=True)
class FrameDone:
    """Composited frame ready to write. ``pixels`` is the raw BGRA buffer
    (width * height * 4 bytes) matching the job's output dimensions."""

    frame_no: int
    pixels: bytes


@dataclass(frozen=True)
class FrameError:
    """A clip raised inside draw() while composing this frame.

    ``exc_repr`` is repr(exc); ``traceback`` is the formatted traceback string.
    The original exception type is not preserved across process boundaries —
    the runner re-raises as RenderError(FFMPEG_FAILURE-style code) with these
    fields in context so the user still sees the underlying traceback.
    """

    frame_no: int
    exc_repr: str
    traceback: str


@dataclass(frozen=True)
class WorkerFatal:
    """Worker hit something it can't recover from (e.g. prepare() raised,
    import error, OOM). Worker exits after sending."""

    worker_id: int
    exc_repr: str
    traceback: str


WorkerMessage = WorkerReady | FrameDone | FrameError | WorkerFatal


# ── Pool interface ───────────────────────────────────────────────────────────


class FrameSink(Protocol):
    """Minimal write surface ParallelFrameRunner uses to emit composited frames.

    VideoWriter satisfies this; tests pass a FakeWriter that records bytes.
    Kept separate from WorkerPool so the runner doesn't depend on ffmpeg in tests.
    """

    def write_frame_bytes(self, pixels: bytes | memoryview) -> None: ...


@runtime_checkable
class WorkerPool(Protocol):
    """Minimal pool surface ParallelFrameRunner depends on.

    Implementations:
      * ProcessWorkerPool — real multiprocessing pool used in production
      * FakePool          — in-process, deterministic, used in unit tests

    Lifecycle: ``start_staggered`` brings worker 0 up first (cache warm),
    then the rest in parallel; resolves when all workers have sent
    ``WorkerReady``. ``submit`` is non-blocking — workers consume requests
    on their own loop and post results back via ``poll`` / ``drain``.
    """

    @property
    def size(self) -> int: ...

    async def start_staggered(self) -> None:
        """Spawn worker 0, await ready, then spawn the rest in parallel."""
        ...

    def submit(self, requests: Iterable[FrameRequest]) -> None:
        """Enqueue frame requests for any worker to pick up. Non-blocking."""
        ...

    async def next_message(self, timeout: float | None = None) -> WorkerMessage | None:
        """Await the next message from any worker. Returns None on timeout.

        Implementations must be cancel-safe (await asyncio.sleep + queue poll
        is fine; blocking calls must be wrapped in run_in_executor).
        """
        ...

    async def shutdown(self, *, terminate_after: float = 15.0) -> None:
        """Send shutdown sentinels, join with timeout, terminate stragglers."""
        ...
