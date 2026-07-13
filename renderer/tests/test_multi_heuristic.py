"""Heuristics for when parallelism=multi actually uses the worker pool."""

from __future__ import annotations

from pixfabrica_core.clips import RenderJob
from pixfabrica_renderer import render as render_mod


def _job(parallelism: str) -> RenderJob:
    return RenderJob(
        title="t",
        description="d",
        width=360,
        height=640,
        fps=24.0,
        duration=1.0,
        parallelism=parallelism,  # type: ignore[arg-type]
    )


def test_should_use_multi_true_for_long_job_at_low_resolution() -> None:
    """Resolution does not disable multi — only frame count and worker count."""
    j = _job("multi")
    assert render_mod._should_use_multi(j, 2400, 8)


def test_should_use_multi_false_below_frame_threshold() -> None:
    j = _job("multi")
    assert not render_mod._should_use_multi(j, 59, 8)


def test_should_use_multi_requires_two_workers() -> None:
    j = _job("multi")
    assert not render_mod._should_use_multi(j, 10_000, 1)


def test_should_use_multi_respects_parallelism_single() -> None:
    j = _job("single")
    assert not render_mod._should_use_multi(j, 10_000, 8)
