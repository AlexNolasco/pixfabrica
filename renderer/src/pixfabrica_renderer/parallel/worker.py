"""Worker process entry point.

A worker is a long-lived child process that:
  1. Reconstructs the RenderJob from JSON, builds JobInfo, runs prepare()
     on the visual side only (sound prepare happens in the parent — its
     timeline data is shipped over IPC).
  2. Loops: pull FrameRequest → composite → push FrameDone (or FrameError).
  3. Exits cleanly on Shutdown.

This module is the multiprocessing target — it must be importable by `spawn`
on Windows. Do NOT use closures from the parent or rely on module-level
mutable state populated by the parent.
"""

from __future__ import annotations

import asyncio
import logging
import os
import traceback
from multiprocessing.queues import Queue as MpQueue
from pathlib import Path
from typing import Any

from pixfabrica_core.audio.bus import AudioBusFrame, AudioTimeline
from pixfabrica_core.clips import JobInfo, PrepareContext, RenderJob, TimeState
from pixfabrica_core.composition.effect_registry import register_effect
from pixfabrica_core.composition.registry import register_clip_type, register_setting_type
from pixfabrica_core.fonts.skia_resolver import warmup_typography_palette
from pixfabrica_core.plugins.discovery import discover_plugins
from pixfabrica_core.theme.color import ColorPalette
from pixfabrica_core.theme.typography import FontPalette
from pixfabrica_renderer.compositor import Compositor
from pixfabrica_renderer.parallel.protocol import (
    FrameDone,
    FrameError,
    FrameRequest,
    Shutdown,
    WorkerFatal,
    WorkerReady,
)


def _ensure_plugins_registered(plugins_dir: str | None) -> None:
    """Workers spawn fresh interpreters — re-discover plugins so the registry
    knows about clip types referenced in the job JSON."""
    discovered, _failed = discover_plugins(Path(plugins_dir) if plugins_dir else None)
    for plugin in discovered:
        for clip_cls in plugin.clip_types:
            register_clip_type(clip_cls)
        for cfg_cls in plugin.project_settings:
            register_setting_type(cfg_cls)
        for effect_cls in plugin.effects:
            register_effect(effect_cls)


def worker_main(
    worker_id: int,
    request_q: MpQueue,
    result_q: MpQueue,
    job_payload: dict[str, Any],
    width: int,
    height: int,
    fps: float,
    locale: str,
    audio_timeline_payload: dict[str, list[dict[str, Any]]],
    plugins_dir: str | None = None,
) -> None:
    """Process target. All args must be picklable.

    ``job_payload`` is ``RenderJob.model_dump(mode="json")`` from the parent
    AFTER theme/typography resolution — the dumped payload already encodes
    the resolved palette/typography so the child does not re-run theme settings.

    ``audio_timeline_payload`` is the parent's resolved AudioTimeline serialized
    via Pydantic — workers reconstruct it instead of re-running sound prepare.

    ``plugins_dir`` is forwarded to discover_plugins() so workers register the
    same clip types as the parent. None → use the discovery default
    (<repo-root>/plugins).
    """
    os.environ["PIXFABRICA_RENDERER_MP_WORKER"] = "1"
    log = logging.getLogger(f"pixfabrica.renderer.parallel.worker.{worker_id}")
    try:
        # Plugins must register before model_validate sees type-id strings,
        # otherwise everything deserializes to UnknownClip.
        _ensure_plugins_registered(plugins_dir)
        # The job_payload was already through _resolve_timeline in the parent
        # (clip.start absolutized, typography scaled). Re-running it here
        # would double-shift starts and double-scale fonts.
        job = RenderJob.model_validate(job_payload, context={"skip_resolve_timeline": True})
        colors = ColorPalette.model_validate(job_payload.get("colors", {}))
        typography = FontPalette.model_validate(job_payload.get("typography", {}))
        ji = JobInfo(
            title=job.title,
            description=job.description,
            width=width,
            height=height,
            fps=fps,
            duration=job.duration,
            colors=colors,
            typography=typography,
            locale=locale,
            output_width=job.width,
            output_height=job.height,
        )
        # Reconstruct audio timeline first so visuals' prepare() can access it
        # via PrepareContext.audio (used by audio-reactive clips to precompute
        # per-frame state — required for stateless draw() under parallelism).
        audio_timeline: AudioTimeline = {
            bus: [AudioBusFrame.model_validate(f) for f in frames]
            for bus, frames in audio_timeline_payload.items()
        }
        prepare_ctx = PrepareContext.from_env(ji, audio=audio_timeline)
        warmup_typography_palette(ji.typography)

        async def _prepare_visuals() -> None:
            await asyncio.gather(*[t.prepare(prepare_ctx) for t in job.tracks])

        asyncio.run(_prepare_visuals())

        compositor = Compositor(job.tracks, ji, audio=audio_timeline)
    except BaseException as exc:  # noqa: BLE001 — must wire any prepare failure back
        result_q.put(
            WorkerFatal(
                worker_id=worker_id,
                exc_repr=repr(exc),
                traceback=traceback.format_exc(),
            )
        )
        return

    result_q.put(WorkerReady(worker_id=worker_id))
    log.info("worker %d ready (pid=%d)", worker_id, os.getpid())

    try:
        while True:
            try:
                msg = request_q.get()
            except (EOFError, OSError):
                break

            if isinstance(msg, Shutdown):
                log.debug("worker %d shutting down", worker_id)
                break

            if not isinstance(msg, FrameRequest):
                log.warning("worker %d got unknown message type %r", worker_id, type(msg).__name__)
                continue

            frame_no = msg.frame_no
            try:
                surface = compositor.composite(TimeState(frame=frame_no, t=frame_no / fps))
                pixels = bytes(surface.toarray())
                result_q.put(FrameDone(frame_no=frame_no, pixels=pixels))
            except BaseException as exc:  # noqa: BLE001 — protect the worker loop
                result_q.put(
                    FrameError(
                        frame_no=frame_no,
                        exc_repr=repr(exc),
                        traceback=traceback.format_exc(),
                    )
                )
    finally:
        compositor.release_worker_resources()
