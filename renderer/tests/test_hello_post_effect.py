"""Hello gallery starter — typewriter text must animate across frames."""

from __future__ import annotations

import asyncio
import json
import zipfile
from pathlib import Path

import numpy as np

from pixfabrica_core.clips import JobInfo, PrepareContext, RenderJob, TimeState
from pixfabrica_core.composition.registry import register_clip_type, register_setting_type
from pixfabrica_core.fonts.skia_resolver import warmup_typography_palette
from pixfabrica_core.plugins.discovery import discover_plugins
from pixfabrica_renderer.compositor import Compositor

_HELLO_BUNDLE = (
    Path(__file__).resolve().parents[2]
    / "api"
    / "media"
    / "gallery"
    / "starters"
    / "hello-world.pixfabrica.zip"
)


def _register_plugins() -> None:
    for plugin in discover_plugins()[0]:
        for clip_cls in plugin.clip_types:
            register_clip_type(clip_cls)
        for cfg_cls in plugin.project_settings:
            register_setting_type(cfg_cls)


def _web_preview_payload() -> dict:
    with zipfile.ZipFile(_HELLO_BUNDLE) as bundle:
        payload = json.loads(bundle.read("project.json"))
    payload["width"] = 360
    payload["height"] = 360
    return payload


async def _composite(job: RenderJob, t: float) -> np.ndarray:
    ji = JobInfo(
        title=job.title,
        description=job.description,
        width=job.width,
        height=job.height,
        fps=job.fps,
        duration=job.duration,
        colors=job.colors,
        typography=job.typography,
        locale=job.locale,
    )
    ctx = PrepareContext.from_env(ji)
    warmup_typography_palette(ji.typography)
    for track in job.tracks:
        await track.prepare(ctx)
    compositor = Compositor(job.tracks, ji)
    frame = int(t * job.fps)
    return np.array(compositor.composite(TimeState(frame=frame, t=t)).toarray())


def test_hello_typewriter_animates_over_time() -> None:
    from pixfabrica_std.text.dynamic_text import DynamicText

    _register_plugins()
    job = RenderJob.model_validate(_web_preview_payload())
    assert job.duration == 3.0
    assert len(job.tracks) == 1

    track = job.tracks[0]
    assert track.clip_type == "std-skia-track"
    text_el = track.clips[0]
    assert isinstance(text_el, DynamicText)
    assert text_el.effect == "typewriter"
    assert text_el.text == "Hello \nWorld"
    assert text_el.type_speed == 12.0

    early = asyncio.run(_composite(job, 0.25))
    late = asyncio.run(_composite(job, 2.5))
    diff = float(np.mean(np.abs(late.astype(np.int16) - early.astype(np.int16))))
    assert diff > 1.0, f"expected visible typewriter progress, mean pixel diff was {diff:.3f}"
