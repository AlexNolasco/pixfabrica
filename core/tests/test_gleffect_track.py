"""GLEffectTrack (std-post-track) validation and RenderJob deserialization."""

from __future__ import annotations

from typing import ClassVar

import pytest
from pydantic import ValidationError

from pixfabrica_core.clips import (
    ClipCategory,
    GLPostProcessClip,
    PrepareContext,
    RenderContext,
    RenderJob,
)
from pixfabrica_core.composition.registry import register_clip_type
from pixfabrica_core.composition.track import GLEffectTrack
from pixfabrica_core.graphics import Rect


class _TestPost(GLPostProcessClip):
    """Minimal GL post clip for core tests (registered at import)."""

    clip_type: ClassVar[str] = "test-gl-post-dummy"
    clip_category: ClassVar[ClipCategory] = ClipCategory.POSTPROCESS

    async def prepare(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        pass

    def draw(self, ctx: RenderContext) -> None:
        pass


register_clip_type(_TestPost)


def _minimal_job(tracks: list[dict]) -> dict:
    return {
        "title": "t",
        "description": "d",
        "tracks": tracks,
    }


def test_std_post_track_deserializes_to_gleffect_track():
    job = RenderJob.model_validate(
        _minimal_job(
            [
                {
                    "id": "post1",
                    "clip_type": "std-post-track",
                    "start": 0.0,
                    "clips": [{"id": "e1", "clip_type": "test-gl-post-dummy"}],
                }
            ]
        )
    )
    assert len(job.tracks) == 1
    assert isinstance(job.tracks[0], GLEffectTrack)


def test_gleffect_track_accepts_empty_clips():
    job = RenderJob.model_validate(
        _minimal_job(
            [
                {
                    "id": "post1",
                    "clip_type": "std-post-track",
                    "start": 0.0,
                    "clips": [],
                }
            ]
        )
    )
    assert isinstance(job.tracks[0], GLEffectTrack)
    assert job.tracks[0].clips == []


def test_gleffect_track_rejects_more_than_one_clip():
    with pytest.raises(ValidationError):
        RenderJob.model_validate(
            _minimal_job(
                [
                    {
                        "id": "post1",
                        "clip_type": "std-post-track",
                        "start": 0.0,
                        "clips": [
                            {"id": "e1", "clip_type": "test-gl-post-dummy"},
                            {"id": "e2", "clip_type": "test-gl-post-dummy"},
                        ],
                    }
                ]
            )
        )


def test_gl_track_rejects_gl_post_process_clip():
    with pytest.raises(ValidationError):
        RenderJob.model_validate(
            _minimal_job(
                [
                    {
                        "id": "gl1",
                        "clip_type": "std-gl-track",
                        "start": 0.0,
                        "clips": [{"id": "e1", "clip_type": "test-gl-post-dummy"}],
                    }
                ]
            )
        )
