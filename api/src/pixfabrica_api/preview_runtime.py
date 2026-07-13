"""Shared preview compositor lifecycle — GL context thread affinity and teardown."""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import skia

from pixfabrica_core.audio.bus import AudioTimeline, align_bus_timeline_to_job
from pixfabrica_core.audio.preview_prepare import sounds_for_preview_prepare
from pixfabrica_core.audio.timeline_store import TimelineMemoryStore
from pixfabrica_core.clips import JobInfo, PrepareContext, RenderJob, TimeState
from pixfabrica_core.composition.track import GLEffectTrack, GLTrack, TrackClip
from pixfabrica_core.fonts.skia_resolver import warmup_typography_palette
from pixfabrica_core.job_effects import tracks_need_gl_context
from pixfabrica_core.prepare_diagnostics import PrepareDiagnostics
from pixfabrica_core.preview_invalidation import ReprepareScope, tracks_needing_prepare
from pixfabrica_core.theme.typography import FontPalette
from pixfabrica_renderer.compositor import Compositor

log = logging.getLogger("pixfabrica.api.preview_runtime")

_gl_executor: ThreadPoolExecutor | None = None
_gl_ops_lock = asyncio.Lock()


def job_uses_gl(job: RenderJob) -> bool:
    return any(isinstance(track, (GLTrack, GLEffectTrack)) for track in job.tracks)


def compositor_uses_gl(compositor: Compositor) -> bool:
    return compositor._gl_ctx is not None


def _get_gl_executor() -> ThreadPoolExecutor:
    global _gl_executor
    if _gl_executor is None:
        _gl_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="preview-gl")
    return _gl_executor


async def release_compositor(compositor: Compositor | None) -> None:
    """Release GPU/Skia worker resources; GL teardown runs on the preview GL thread."""
    if compositor is None:
        return
    async with _gl_ops_lock:
        if compositor_uses_gl(compositor):
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(_get_gl_executor(), compositor.release_worker_resources)
        else:
            compositor.release_worker_resources()


async def release_compositor_gl(compositor: Compositor | None) -> None:
    """Release only the GL context — keeps prepared Skia tracks alive for narrow reprepare."""
    if compositor is None or not compositor_uses_gl(compositor):
        return
    loop = asyncio.get_running_loop()
    async with _gl_ops_lock:
        await loop.run_in_executor(_get_gl_executor(), compositor.release_gl_context)


@dataclass(frozen=True, slots=True)
class PrepareOptions:
    scope: ReprepareScope = ReprepareScope.FULL
    reuse_audio_timeline: AudioTimeline | None = None
    old_tracks: list | None = None


def typography_for_preview_surface(
    typography: FontPalette,
    *,
    job_height: int,
    preview_height: int,
    scale_to_preview: bool,
) -> FontPalette:
    """Return typography for a preview surface while preserving full-res snapshots."""
    if not scale_to_preview:
        return typography
    safe_job_h = max(1, int(job_height))
    safe_preview_h = max(1, int(preview_height))
    factor = safe_preview_h / safe_job_h
    if factor == 1.0:
        return typography
    return typography.scale(factor)


async def prepare_compositor(
    job: RenderJob,
    preview_w: int,
    preview_h: int,
    *,
    scale_typography_to_preview: bool = True,
    diagnostics: PrepareDiagnostics | None = None,
    timeline_store: TimelineMemoryStore | None = None,
    prepare_options: PrepareOptions | None = None,
) -> tuple[Compositor, PrepareDiagnostics]:
    """Run prepare() on all tracks; GL context create/use stay on one worker thread."""
    diag = diagnostics if diagnostics is not None else PrepareDiagnostics()
    opts = prepare_options or PrepareOptions()
    if job_uses_gl(job) or tracks_need_gl_context(job.tracks, for_preview=True):
        loop = asyncio.get_running_loop()

        def run() -> tuple[Compositor, PrepareDiagnostics]:
            return asyncio.run(
                _prepare_job(
                    job,
                    preview_w,
                    preview_h,
                    scale_typography_to_preview=scale_typography_to_preview,
                    diagnostics=diag,
                    timeline_store=timeline_store,
                    prepare_options=opts,
                )
            )

        async with _gl_ops_lock:
            return await loop.run_in_executor(_get_gl_executor(), run)
    return await _prepare_job(
        job,
        preview_w,
        preview_h,
        scale_typography_to_preview=scale_typography_to_preview,
        diagnostics=diag,
        timeline_store=timeline_store,
        prepare_options=opts,
    )


async def _prepare_job(
    job: RenderJob,
    preview_w: int,
    preview_h: int,
    *,
    scale_typography_to_preview: bool,
    diagnostics: PrepareDiagnostics,
    timeline_store: TimelineMemoryStore | None = None,
    prepare_options: PrepareOptions | None = None,
) -> tuple[Compositor, PrepareDiagnostics]:
    opts = prepare_options or PrepareOptions()
    from pixfabrica_core.project_variables import merge_project_variable_warnings

    merge_project_variable_warnings(job, diagnostics)
    warmup_typography_palette(job.typography)
    preview_typography = typography_for_preview_surface(
        job.typography,
        job_height=job.height,
        preview_height=preview_h,
        scale_to_preview=scale_typography_to_preview,
    )
    preview_job_info = JobInfo(
        title=job.title,
        description=job.description,
        width=preview_w,
        height=preview_h,
        fps=job.fps,
        duration=job.duration,
        locale=job.locale,
        colors=job.colors,
        typography=preview_typography,
        output_width=job.width,
        output_height=job.height,
    )

    audio_timeline: AudioTimeline | None = opts.reuse_audio_timeline
    if audio_timeline is None:
        sounds_prepare_ctx = PrepareContext.from_env(
            preview_job_info,
            for_preview=True,
            diagnostics=diagnostics,
            timeline_store=timeline_store,
        )
        preview_sounds = sounds_for_preview_prepare(job)
        if preview_sounds:
            await asyncio.gather(*[s.prepare(sounds_prepare_ctx) for s in preview_sounds])

        total_frames = max(1, int(job.duration * job.fps))
        audio_timeline = {}
        for sound in job.sounds:
            if (
                not sound.enabled
                or not sound.bus.strip()
                or not sound.is_ready
                or not sound.timeline
            ):
                continue
            audio_timeline[sound.bus] = align_bus_timeline_to_job(
                sound.timeline,
                sound_start_seconds=sound.start,
                job_total_frames=total_frames,
                fps=job.fps,
            )
    else:
        log.debug("preview prepare: reusing audio timeline (%d buses)", len(audio_timeline))

    merged_tracks, tracks_to_prepare = tracks_needing_prepare(
        job,
        scope=opts.scope,
        old_tracks=opts.old_tracks,
    )

    prepare_ctx = PrepareContext.from_env(
        preview_job_info, audio=audio_timeline, diagnostics=diagnostics
    )
    if tracks_to_prepare:
        prepare_results = await asyncio.gather(
            *[track.prepare(prepare_ctx) for track in tracks_to_prepare],
            return_exceptions=True,
        )
        for track, result in zip(tracks_to_prepare, prepare_results, strict=True):
            if isinstance(result, BaseException):
                log.warning(
                    "preview prepare: track %s failed — %s",
                    getattr(track, "id", type(track).__name__),
                    result,
                )
    elif opts.scope == ReprepareScope.GL_CONTEXT_ONLY:
        log.debug("preview prepare: reusing %d Skia track(s), GL only", len(merged_tracks))

    return (
        Compositor(merged_tracks, preview_job_info, audio=audio_timeline, for_preview=True),
        diagnostics,
    )


def skia_surface_rgba_bytes(surface: skia.Surface) -> bytes:
    """Read Skia surface pixels as RGBA for canvas putImageData (Skia is BGRA on Windows)."""
    bgra = surface.toarray()
    rgba = bgra.copy()
    rgba[:, :, [0, 2]] = rgba[:, :, [2, 0]]
    return rgba.tobytes()


def render_frame(compositor: Compositor, t: float, fps: float) -> bytes:
    """Render one frame and return raw RGBA bytes."""
    frame = int(t * fps)
    surface = compositor.composite(TimeState(frame=frame, t=t))
    return skia_surface_rgba_bytes(surface)


async def prepare_clip_compositor(
    track: TrackClip,
    job_info: JobInfo,
    audio: AudioTimeline | None = None,
    diagnostics: PrepareDiagnostics | None = None,
    *,
    variable_warnings: list | None = None,
) -> tuple[Compositor, PrepareDiagnostics]:
    """Prepare a single-track compositor for clip preview (with optional demo audio)."""
    diag = diagnostics if diagnostics is not None else PrepareDiagnostics()
    if variable_warnings:
        diag.ingest(variable_warnings)
    uses_gl = tracks_need_gl_context([track], for_preview=True)

    async def build() -> tuple[Compositor, PrepareDiagnostics]:
        ctx = PrepareContext.from_env(job_info, audio=audio or {}, diagnostics=diag)
        await track.prepare(ctx)
        return Compositor([track], job_info, audio=audio, for_preview=True), diag

    if uses_gl:
        loop = asyncio.get_running_loop()
        async with _gl_ops_lock:
            return await loop.run_in_executor(_get_gl_executor(), lambda: asyncio.run(build()))
    return await build()


async def render_preview_frame(compositor: Compositor, t: float, fps: float) -> bytes:
    """Composite one preview frame without blocking the API event loop."""
    loop = asyncio.get_running_loop()
    if compositor_uses_gl(compositor):
        async with _gl_ops_lock:
            return await loop.run_in_executor(_get_gl_executor(), render_frame, compositor, t, fps)
    return await loop.run_in_executor(None, render_frame, compositor, t, fps)
