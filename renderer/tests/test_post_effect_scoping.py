"""Regression tests — post effects only sample tracks beneath them in paint order."""

from __future__ import annotations

import asyncio
from typing import ClassVar

import numpy as np
import pytest
import skia

from pixfabrica_core.clips import (
    ClipCategory,
    GLPostProcessClip,
    JobInfo,
    PrepareContext,
    RenderContext,
    RenderJob,
    TimeState,
)
from pixfabrica_core.composition.registry import register_clip_type, register_setting_type
from pixfabrica_core.composition.track import GLEffectTrack, GLTrack, SkiaTrack
from pixfabrica_core.fonts.skia_resolver import warmup_typography_palette
from pixfabrica_core.graphics import Rect
from pixfabrica_core.plugins.discovery import discover_plugins
from pixfabrica_core.theme.color import Color, ColorPalette
from pixfabrica_core.theme.typography import FontPalette
from pixfabrica_renderer.compositor import Compositor
from pixfabrica_renderer.gl_context import GLContext

_FRAME = 64


class _TestMagentaPost(GLPostProcessClip):
    """Full-frame magenta fill — makes it obvious when a post pass overwrote upper tracks."""

    clip_type: ClassVar[str] = "test-magenta-post"
    clip_category: ClassVar[ClipCategory] = ClipCategory.POSTPROCESS

    async def prepare(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        pass

    def draw(self, ctx: RenderContext) -> None:
        ctx.canvas.clear(1.0, 0.0, 1.0, 1.0)


register_clip_type(_TestMagentaPost)


def _register_std_plugins() -> None:
    for plugin in discover_plugins()[0]:
        for clip_cls in plugin.clip_types:
            register_clip_type(clip_cls)
        for cfg_cls in plugin.project_settings:
            register_setting_type(cfg_cls)


def _job_info() -> JobInfo:
    return JobInfo(
        title="post-scope",
        description="",
        width=_FRAME,
        height=_FRAME,
        fps=30.0,
        duration=1.0,
        locale="en",
        colors=ColorPalette(
            primary=Color("#ff0000"),
            secondary=Color("#ff0000"),
            tertiary=Color("#ff0000"),
            accent=Color("#00ff00"),
            background=Color("#ff0000"),
            neutral=Color("#000000"),
            neutral_variant=Color("#888888"),
        ),
        typography=FontPalette(),
    )


def _mid_stack_job() -> dict:
    return {
        "title": "post-scope",
        "description": "",
        "width": _FRAME,
        "height": _FRAME,
        "fps": 30,
        "duration": 1,
        "locale": "en",
        "colors": _job_info().colors.model_dump(mode="json"),
        "tracks": [
            {
                "clip_type": "std-skia-track",
                "id": "back",
                "start": 0,
                "duration": 1,
                "clips": [
                    {
                        "id": "bg",
                        "clip_type": "std-solid-background",
                        "color": "primary",
                        "height": 1,
                        "offset_y": 0,
                        "opacity": 1,
                        "start": 0,
                        "duration": None,
                    }
                ],
            },
            {
                "clip_type": "std-post-track",
                "id": "post",
                "start": 0,
                "duration": 1,
                "clips": [
                    {
                        "id": "fx",
                        "clip_type": "test-magenta-post",
                        "start": 0,
                        "duration": None,
                    }
                ],
            },
            {
                "clip_type": "std-skia-track",
                "id": "front",
                "start": 0,
                "duration": 1,
                "clips": [
                    {
                        "id": "top",
                        "clip_type": "std-solid-background",
                        "color": "accent",
                        "height": 0.5,
                        "offset_y": 0,
                        "opacity": 1,
                        "start": 0,
                        "duration": None,
                    }
                ],
            },
        ],
    }


async def _composite_rgba(job: RenderJob, t: float = 0.0) -> np.ndarray:
    ji = _job_info()
    ctx = PrepareContext.from_env(ji)
    warmup_typography_palette(ji.typography)
    for track in job.tracks:
        await track.prepare(ctx)
    compositor = Compositor(job.tracks, ji)
    return np.array(compositor.composite(TimeState(frame=0, t=t)).toarray())


@pytest.fixture(scope="module", autouse=True)
def _plugins() -> None:
    _register_std_plugins()


def test_composite_paints_tracks_in_storage_order(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reordering all post tracks to the end (d3dc0579) would fail this test."""
    painted: list[str] = []
    original = Compositor._render_track

    def _spy(
        self: Compositor, track: SkiaTrack | GLTrack | GLEffectTrack, time: TimeState, canvas
    ) -> None:
        painted.append(track.id)
        original(self, track, time, canvas)

    monkeypatch.setattr(Compositor, "_render_track", _spy)

    tracks = [
        SkiaTrack(id="skia-0", start=0.0, duration=1.0, clips=[]),
        GLTrack(id="gl-1", start=0.0, duration=1.0, clips=[]),
        GLEffectTrack(id="post-2", start=0.0, duration=1.0, clips=[]),
        SkiaTrack(id="skia-3", start=0.0, duration=1.0, clips=[]),
    ]
    Compositor(tracks, _job_info()).composite(TimeState(frame=0, t=0.0))
    assert painted == ["skia-0", "gl-1", "post-2", "skia-3"]


def _snapshot_surface(surface: skia.Surface) -> np.ndarray:
    surface.getCanvas().flush()
    return np.array(surface.makeImageSnapshot()).copy()


def test_mid_stack_post_snapshots_only_tracks_beneath(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Post at index 2 must snapshot [0] only — not the front skia track at index 3."""
    snapshots: list[np.ndarray] = []
    original_upload = GLContext.upload_skia_surface

    def _spy_upload(self: GLContext, surface: skia.Surface) -> object:
        snapshots.append(_snapshot_surface(surface))
        return original_upload(self, surface)

    monkeypatch.setattr(GLContext, "upload_skia_surface", _spy_upload)

    job = RenderJob.model_validate(_mid_stack_job())
    asyncio.run(_composite_rgba(job))

    assert len(snapshots) == 1
    snap = snapshots[0]
    # Skia snapshots are BGRA: red back is channel 2, green front is channel 1.
    assert int(np.median(snap[:, :, 2])) >= 200, "snapshot should still be the red back track"
    assert int(np.median(snap[:, :, 1])) <= 20, (
        "snapshot must not include green from the front track"
    )


def test_post_last_snapshots_tracks_above_it(monkeypatch: pytest.MonkeyPatch) -> None:
    """Moving post to the end (d3dc0579) feeds it pixels from upper tracks too."""
    snapshots: list[np.ndarray] = []
    original_upload = GLContext.upload_skia_surface

    def _spy_upload(self: GLContext, surface: skia.Surface) -> object:
        snapshots.append(_snapshot_surface(surface))
        return original_upload(self, surface)

    monkeypatch.setattr(GLContext, "upload_skia_surface", _spy_upload)

    payload = _mid_stack_job()
    payload["tracks"] = [payload["tracks"][0], payload["tracks"][2], payload["tracks"][1]]
    job = RenderJob.model_validate(payload)
    asyncio.run(_composite_rgba(job))

    assert len(snapshots) == 1
    snap = snapshots[0]
    # Front paints green into the visual top half before post runs in this order.
    visual_top_row = 8
    assert int(snap[visual_top_row, _FRAME // 2, 1]) >= 200, (
        "post-last snapshot should include front-track green"
    )


def test_two_post_tracks_keep_relative_paint_order(monkeypatch: pytest.MonkeyPatch) -> None:
    painted: list[str] = []
    original = Compositor._render_track

    def _spy(
        self: Compositor, track: SkiaTrack | GLTrack | GLEffectTrack, time: TimeState, canvas
    ) -> None:
        painted.append(track.id)
        original(self, track, time, canvas)

    monkeypatch.setattr(Compositor, "_render_track", _spy)

    tracks = [
        SkiaTrack(id="skia-0", start=0.0, duration=1.0, clips=[]),
        GLEffectTrack(id="post-a", start=0.0, duration=1.0, clips=[]),
        SkiaTrack(id="skia-2", start=0.0, duration=1.0, clips=[]),
        GLEffectTrack(id="post-b", start=0.0, duration=1.0, clips=[]),
    ]
    Compositor(tracks, _job_info()).composite(TimeState(frame=0, t=0.0))
    assert painted == ["skia-0", "post-a", "skia-2", "post-b"]
