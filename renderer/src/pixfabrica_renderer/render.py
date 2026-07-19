"""render_job() — the single entry point for rendering a RenderJob to video.

Both the CLI and the API call this function. It is an async generator that
yields RenderProgress events so callers can stream progress (Rich bar / WebSocket).

Blocking note: the serial frame loop (compositor.composite + writer.write_frame) is
synchronous. For API use, run this generator inside asyncio.get_event_loop()
.run_in_executor() or a background Task to avoid blocking the event loop.

Parallelism: when ``job.parallelism == "multi"``, render_job() dispatches to a
ProcessWorkerPool sized to ``cpu_count - 2`` (min 1). It auto-falls back to the
serial loop for very short jobs (below a small frame threshold), single-CPU
systems, or pool-init failures.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pixfabrica_core.audio.bus import (
    AudioTimeline,
    align_bus_timeline_to_job,
)
from pixfabrica_core.clips import JobInfo, PrepareContext, RenderJob, TimeState, VisualClip
from pixfabrica_core.composition.config import ThemeContext
from pixfabrica_core.composition.track import GLEffectTrack, GLTrack
from pixfabrica_core.composition.unknown import UnknownClip, UnknownEffect, UnknownProjectSetting
from pixfabrica_core.errors import RenderError, RenderErrorCode
from pixfabrica_core.fonts.skia_resolver import warmup_typography_palette
from pixfabrica_core.job_assets import run_job_asset_contributor_phase
from pixfabrica_core.job_effects import (
    job_requires_single_process,
    resolve_parallelism,
    tracks_need_gl_context,
)
from pixfabrica_core.plugins.discovery import discover_plugins
from pixfabrica_core.progress import RenderProgress
from pixfabrica_renderer.audio_mix import mix_sounds
from pixfabrica_renderer.compositor import Compositor
from pixfabrica_renderer.gl_probe import gl_available
from pixfabrica_renderer.parallel import ParallelFrameRunner, ProcessWorkerPool
from pixfabrica_renderer.video import VideoWriter

if TYPE_CHECKING:
    pass

log = logging.getLogger("pixfabrica.renderer.render")


def _dump_clip_type(clip: Any, *, type_key: str, type_value: str) -> dict:
    """Dump a model using its concrete class, re-attaching the ClassVar type id."""
    payload = clip.model_dump(mode="json")
    payload[type_key] = type_value
    return payload


def _dump_visual_clip(el: Any) -> dict:
    payload = _dump_clip_type(el, type_key="clip_type", type_value=type(el).clip_type)
    if isinstance(el, VisualClip) and el.effects:
        payload["effects"] = [_dump_effect(fx) for fx in el.effects]
    return payload


def _dump_effect(fx: Any) -> dict:
    return _dump_clip_type(fx, type_key="effect_type", type_value=type(fx).effect_type)


def _dump_project_setting(setting: Any) -> dict:
    return _dump_clip_type(setting, type_key="setting_type", type_value=type(setting).setting_type)


def _dump_sound(sound: Any) -> dict:
    return _dump_clip_type(sound, type_key="sound_type", type_value=type(sound).sound_type)


def _dump_track(track: Any) -> dict:
    """Same trick for a TrackClip plus its polymorphic children and track effects."""
    payload = _dump_clip_type(track, type_key="clip_type", type_value=type(track).clip_type)
    payload["clips"] = [_dump_visual_clip(el) for el in track.clips]
    if getattr(track, "effects", None):
        payload["effects"] = [_dump_effect(fx) for fx in track.effects]
    return payload


# Below this many frames, multi-worker spawn + per-worker prepare cost
# more than the serial render itself. Picked to comfortably cover the
# "preview-to-mp4" workflow (≤ 1 s clips).
_MULTI_FALLBACK_FRAME_THRESHOLD = 60

# Leave 2 cores for the OS, ffmpeg encoder, and the parent's drain thread.
_RESERVED_CORES = 2


def _check_unknown_plugins(job: RenderJob) -> None:
    """Raise RenderError(UNKNOWN_PLUGIN) if any clips, effects, or settings are unrecognised."""
    if isinstance(job.theme, UnknownProjectSetting):
        raise RenderError(RenderErrorCode.UNKNOWN_PLUGIN, {"clip_type": job.theme.raw_setting_type})
    if isinstance(job.typography_setting, UnknownProjectSetting):
        raise RenderError(
            RenderErrorCode.UNKNOWN_PLUGIN, {"clip_type": job.typography_setting.raw_setting_type}
        )
    for track in job.tracks:
        for fx in track.effects:
            if isinstance(fx, UnknownEffect):
                raise RenderError(
                    RenderErrorCode.UNKNOWN_PLUGIN, {"effect_type": fx.raw_effect_type}
                )
        for clip in track.clips:
            if isinstance(clip, UnknownClip):
                raise RenderError(RenderErrorCode.UNKNOWN_PLUGIN, {"clip_type": clip.raw_clip_type})
            if isinstance(clip, VisualClip):
                for fx in clip.effects:
                    if isinstance(fx, UnknownEffect):
                        raise RenderError(
                            RenderErrorCode.UNKNOWN_PLUGIN, {"effect_type": fx.raw_effect_type}
                        )


def _resolve_worker_count() -> int:
    """Honor user wish for "no artificial cap": use all but 2 cores, min 1."""
    cpu = os.cpu_count() or 1
    return max(1, cpu - _RESERVED_CORES)


def _should_use_multi(job: RenderJob, total_frames: int, workers: int) -> bool:
    """Apply the auto-fallback rules from the design pass."""
    if resolve_parallelism(job) != "multi":
        return False
    if workers < 2:
        log.info("parallelism=multi requested but only %d worker available — using single", workers)
        return False
    if total_frames < _MULTI_FALLBACK_FRAME_THRESHOLD:
        log.info(
            "parallelism=multi requested but only %d frames (< %d) — using single",
            total_frames,
            _MULTI_FALLBACK_FRAME_THRESHOLD,
        )
        return False
    return True


async def render_job(
    job: RenderJob,
    output: Path,
    *,
    width: int | None = None,
    height: int | None = None,
    fps: float | None = None,
    cancel: threading.Event | None = None,
    plugins_dir: str | None = None,
) -> AsyncIterator[RenderProgress]:
    """Render *job* to *output*, yielding progress events.

    CLI overrides (width/height/fps) apply to VideoWriter and Compositor only —
    the job model is not re-validated, so tracks keep their design-time layout.

    Raises:
        RenderError: on any known failure (plugin, param, asset, FFmpeg, etc.)
    """
    _check_unknown_plugins(job)
    if not gl_available() and tracks_need_gl_context(job.tracks):
        raise RenderError(
            RenderErrorCode.GL_UNAVAILABLE,
            {"detail": "Install GPU drivers or run on a host with OpenGL support."},
        )
    if job_requires_single_process(job) and job.parallelism == "multi":
        log.warning("singleton effect present — forcing parallelism=single for this render")

    effective_width = width if width is not None else job.width
    effective_height = height if height is not None else job.height
    effective_fps = fps if fps is not None else job.fps
    total_frames = round(job.duration * effective_fps)

    yield RenderProgress(stage="prepare", frame=0, total=total_frames, pct=0)

    # ── Prepare phase ────────────────────────────────────────────────────────

    colors = job.colors
    typography = job.typography
    if effective_height != job.height:
        typography = typography.scale(effective_height / job.height)

    bootstrap_ji = JobInfo(
        title=job.title,
        description=job.description,
        width=effective_width,
        height=effective_height,
        fps=effective_fps,
        duration=job.duration,
        colors=colors,
        typography=typography,
        locale=job.locale,
        output_width=job.width,
        output_height=job.height,
    )

    prepare_ctx = PrepareContext.from_env(bootstrap_ji, cancel=cancel)

    if (job.theme is not None and job.theme.enabled) or (
        job.typography_setting is not None and job.typography_setting.enabled
    ):
        theme_ctx = ThemeContext(
            width=effective_width,
            height=effective_height,
            temp_dir=prepare_ctx.temp_dir,
            cache_dir=prepare_ctx.cache_dir,
            cancel=cancel,
        )
        if job.theme is not None and job.theme.enabled:
            colors = await job.theme.resolve(theme_ctx)
        if job.typography_setting is not None and job.typography_setting.enabled:
            base = await job.typography_setting.resolve(theme_ctx)
            typography = base.scale(effective_height / job.reference_height)

    ji = JobInfo(
        title=job.title,
        description=job.description,
        width=effective_width,
        height=effective_height,
        fps=effective_fps,
        duration=job.duration,
        colors=colors,
        typography=typography,
        locale=job.locale,
        output_width=job.width,
        output_height=job.height,
    )
    sounds_prepare_ctx = PrepareContext.from_env(ji, cancel=cancel)

    try:
        # Sounds prepare first so their resolved timeline is available to
        # visuals' prepare() (audio-reactive clips precompute per-frame state).
        await asyncio.gather(
            *[s.prepare(sounds_prepare_ctx) for s in job.sounds],
        )
    except OSError as exc:
        raise RenderError(
            RenderErrorCode.MISSING_ASSET,
            {"path": str(exc.filename or ""), "detail": exc.strerror},
        ) from exc

    # ── Audio mix ────────────────────────────────────────────────────────────

    audio_timeline: AudioTimeline = {}
    for s in job.sounds:
        if not s.enabled or not s.bus.strip() or not s.is_ready or not s.timeline:
            continue
        audio_timeline[s.bus] = align_bus_timeline_to_job(
            s.timeline,
            sound_start_seconds=s.start,
            job_total_frames=total_frames,
            fps=effective_fps,
        )

    audio_path = mix_sounds(job.sounds, job.duration, sounds_prepare_ctx.temp_dir / "mixed.wav")

    workers = _resolve_worker_count()
    use_multi = _should_use_multi(job, total_frames, workers)
    parallelism_effective: Literal["single", "multi"] = "multi" if use_multi else "single"

    prepare_ctx = PrepareContext.from_env(ji, cancel=cancel, audio=audio_timeline)
    warmup_typography_palette(ji.typography)
    plugins_path = Path(plugins_dir) if plugins_dir else None
    discovered_plugins, _ = discover_plugins(plugins_path)
    await run_job_asset_contributor_phase(job, prepare_ctx, discovered_plugins)
    try:
        # Serial (or multi fallback): parent process owns job.tracks and must
        # prepare them before Compositor touches them.
        #
        # True multi: each worker deserializes its own job copy and runs the
        # same prepare() there (GL/Skia contexts cannot be shared across
        # processes). Running prepare again in the parent only duplicates CPU,
        # cache I/O, and log noise — skip it. If the pool fails to start, we
        # prepare below right before the serial fallback loop.
        #
        # Note: after a successful multi render, in-memory ``job.tracks`` in
        # this process may not hold prepare-time caches (images, GL programs,
        # precomputed arrays); only worker copies do.
        if not use_multi:
            await asyncio.gather(*[t.prepare(prepare_ctx) for t in job.tracks])
        else:
            log.debug(
                "skipping parent visual prepare — %d worker process(es) will prepare",
                workers,
            )
            await asyncio.gather(*[t.ensure_layout(prepare_ctx) for t in job.tracks])
    except OSError as exc:
        raise RenderError(
            RenderErrorCode.MISSING_ASSET,
            {"path": str(exc.filename or ""), "detail": exc.strerror},
        ) from exc

    # ── Render loop ──────────────────────────────────────────────────────────

    try:
        output.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RenderError(
            RenderErrorCode.OUTPUT_WRITE_ERROR, {"path": str(output), "detail": str(exc)}
        ) from exc

    try:
        with VideoWriter(
            output,
            effective_width,
            effective_height,
            effective_fps,
            audio_path,
            export_quality=job.export_quality,
            video_encoder=job.video_encoder,
        ) as writer:
            if use_multi:
                async for evt in _render_loop_parallel(
                    job,
                    ji,
                    audio_timeline,
                    writer,
                    total_frames,
                    workers,
                    cancel,
                    plugins_dir,
                    prepare_ctx,
                ):
                    yield evt
            else:
                async for evt in _render_loop_serial(
                    job,
                    ji,
                    audio_timeline,
                    writer,
                    total_frames,
                    effective_fps,
                    cancel,
                    parallelism_effective,
                ):
                    yield evt

    except RenderError:
        raise
    except RuntimeError as exc:
        raise RenderError(RenderErrorCode.FFMPEG_FAILURE, {"detail": str(exc)}) from exc
    except OSError as exc:
        raise RenderError(
            RenderErrorCode.OUTPUT_WRITE_ERROR, {"path": str(output), "detail": str(exc)}
        ) from exc

    yield RenderProgress(stage="done", frame=total_frames, total=total_frames, pct=100)


async def _render_loop_serial(
    job: RenderJob,
    ji: JobInfo,
    audio_timeline: dict,
    writer: VideoWriter,
    total_frames: int,
    effective_fps: float,
    cancel: threading.Event | None,
    parallelism_effective: Literal["single", "multi"],
) -> AsyncIterator[RenderProgress]:
    """Original in-process loop. Used when parallelism="single" or fallback."""
    compositor = Compositor(job.tracks, ji, audio=audio_timeline)
    tagged_parallelism = False
    for frame in range(total_frames):
        if cancel and cancel.is_set():
            yield RenderProgress(
                stage="cancelled",
                frame=frame,
                total=total_frames,
                pct=int(frame / total_frames * 100),
            )
            raise RenderError(RenderErrorCode.CANCELLED)

        surface = compositor.composite(TimeState(frame=frame, t=frame / effective_fps))
        writer.write_frame(surface)

        pct = int((frame + 1) / total_frames * 100)
        if not tagged_parallelism:
            tagged_parallelism = True
            yield RenderProgress(
                stage="render",
                frame=frame + 1,
                total=total_frames,
                pct=pct,
                parallelism_effective=parallelism_effective,
            )
        else:
            yield RenderProgress(stage="render", frame=frame + 1, total=total_frames, pct=pct)


async def _render_loop_parallel(
    job: RenderJob,
    ji: JobInfo,
    audio_timeline: dict,
    writer: VideoWriter,
    total_frames: int,
    workers: int,
    cancel: threading.Event | None,
    plugins_dir: str | None,
    prepare_ctx: PrepareContext,
) -> AsyncIterator[RenderProgress]:
    """Multi-process render loop driven by ParallelFrameRunner."""
    if any(isinstance(t, (GLTrack, GLEffectTrack)) for t in job.tracks):
        log.warning(
            "parallelism=multi with GL or GL effect tracks — speedup is driver-dependent. "
            "If you see worse-than-single performance, set parallelism='single'."
        )

    # Two Pydantic gotchas force a hand-rolled payload here:
    #   1. ClassVar type ids (clip_type, effect_type, setting_type, sound_type) aren't in model_dump.
    #   2. Tracks declare clips: list[Clip], so Pydantic dumps each
    #      clip using the BASE class fields only (subclass-specific fields
    #      like `text` get silently dropped). Same story for the theme /
    #      typography_setting fields typed as ThemeSetting | None.
    # Walk the live job and dump each polymorphic clip with its concrete class.
    job_payload = job.model_dump(mode="json")
    job_payload["tracks"] = [_dump_track(t) for t in job.tracks]
    job_payload["sounds"] = [_dump_sound(s) for s in job.sounds]
    if job.theme is not None:
        job_payload["theme"] = _dump_project_setting(job.theme)
    if job.typography_setting is not None:
        job_payload["typography_setting"] = _dump_project_setting(job.typography_setting)

    audio_payload = {
        bus: [f.model_dump(mode="json") for f in frames] for bus, frames in audio_timeline.items()
    }

    pool: ProcessWorkerPool | None = None
    try:
        pool = ProcessWorkerPool(
            size=workers,
            job_payload=job_payload,
            width=ji.width,
            height=ji.height,
            fps=ji.fps,
            locale=ji.locale,
            audio_timeline_payload=audio_payload,
            plugins_dir=plugins_dir,
        )
        try:
            await pool.start_staggered()
        except Exception as exc:
            log.warning("worker pool failed to start (%s); falling back to serial render", exc)
            await pool.shutdown()
            pool = None
            # Parent skipped visual prepare expecting workers to do it — run now.
            try:
                await asyncio.gather(*[t.prepare(prepare_ctx) for t in job.tracks])
            except OSError as ose:
                raise RenderError(
                    RenderErrorCode.MISSING_ASSET,
                    {"path": str(ose.filename or ""), "detail": ose.strerror},
                ) from ose
            async for evt in _render_loop_serial(
                job,
                ji,
                audio_timeline,
                writer,
                total_frames,
                ji.fps,
                cancel,
                "single",
            ):
                yield evt
            return

        runner = ParallelFrameRunner(pool=pool, total_frames=total_frames)
        tagged_parallelism = False
        async for evt in runner.run(writer, cancel=cancel):
            if not tagged_parallelism and evt.stage == "render":
                evt = evt.model_copy(update={"parallelism_effective": "multi"})
                tagged_parallelism = True
            yield evt
    finally:
        if pool is not None:
            await pool.shutdown()
