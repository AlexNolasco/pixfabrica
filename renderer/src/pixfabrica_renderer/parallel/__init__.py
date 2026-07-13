"""Parallel rendering: ProcessWorkerPool + ParallelFrameRunner.

Public surface re-exports the runner, pool, and protocol types. Tests can
import ``protocol`` for the WorkerPool interface to inject FakePool.
"""

from pixfabrica_renderer.parallel.pool import ProcessWorkerPool
from pixfabrica_renderer.parallel.protocol import (
    FrameDone,
    FrameError,
    FrameRequest,
    FrameSink,
    Shutdown,
    WorkerFatal,
    WorkerMessage,
    WorkerPool,
    WorkerReady,
)
from pixfabrica_renderer.parallel.runner import ParallelFrameRunner

__all__ = [
    "FrameDone",
    "FrameError",
    "FrameRequest",
    "FrameSink",
    "ParallelFrameRunner",
    "ProcessWorkerPool",
    "Shutdown",
    "WorkerFatal",
    "WorkerMessage",
    "WorkerPool",
    "WorkerReady",
]
