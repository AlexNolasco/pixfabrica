from __future__ import annotations

import logging
import os
import threading
import time as _time
from contextlib import suppress
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from pixfabrica_renderer.video import VideoWriter

import skia

from pixfabrica_core.audio.bus import (
    AudioBusFrame,
    AudioTimeline,
    resolve_audio_bus_frame_for_clip,
)
from pixfabrica_core.audio.mixin import AudioVisualMixin
from pixfabrica_core.clips import GLPostProcessClip, JobInfo, RenderContext, TimeState, VisualClip
from pixfabrica_core.composition.track import (
    GLEffectTrack,
    GLTrack,
    TrackClip,
    TrackTransition,
    TransitionType,
)
from pixfabrica_core.easing import apply_easing
from pixfabrica_core.graphics import Rect
from pixfabrica_core.job_effects import chain_backend_for_clip, tracks_need_gl_context
from pixfabrica_core.theme.color import ColorToken, resolve_color
from pixfabrica_renderer.effect_pipeline import (
    render_gl_clip_with_effects,
    render_skia_clip_with_effects,
    render_track_with_track_effects,
    track_needs_effect_pipeline,
    visual_clip_needs_effect_pipeline,
)
from pixfabrica_renderer.gl_context import GLContext


class RenderProgress(Protocol):
    def __call__(self, frame: int, total: int) -> None: ...


# Slide/wipe offsets per direction: (dx_multiplier, dy_multiplier)
_DIR_VECTORS: dict[str, tuple[float, float]] = {
    "left": (-1.0, 0.0),
    "right": (1.0, 0.0),
    "up": (0.0, -1.0),
    "down": (0.0, 1.0),
}


class Compositor:
    """
    Owns a single reused Skia surface and (if needed) one GL context.
    Tracks render in array order — painter's model.
    Transitions are applied per-track as intro/outro effects.
    """

    def __init__(
        self,
        tracks: list[TrackClip],
        job_info: JobInfo,
        audio: AudioTimeline | None = None,
        *,
        for_preview: bool = False,
    ) -> None:
        self._tracks = tracks
        self._job_info = job_info
        self._audio: AudioTimeline = audio or {}
        self._for_preview = for_preview
        self._track_rect = Rect(0, 0, job_info.width, job_info.height)
        self._surface = skia.Surface(job_info.width, job_info.height)
        self._log = logging.getLogger("pixfabrica.compositor")

        # Reusable offscreen surface for blur transitions (allocated lazily)
        self._blur_surface: skia.Surface | None = None

        self._needs_gl = tracks_need_gl_context(tracks, for_preview=for_preview)
        self._gl_ctx: GLContext | None = None
        if self._needs_gl:
            self._gl_ctx = GLContext(job_info.width, job_info.height)

        # Per-track wall-clock accumulator (seconds) + frame counter for periodic
        # summary logging. Worker processes each have their own Compositor, so we
        # log per-PID summaries to make multi-worker timing observable.
        self._track_times: dict[str, float] = {}
        self._frames_composited: int = 0
        self._timing_log_every: int = int(os.environ.get("PIXFABRICA_TIMING_EVERY", "200"))
        self._post_paint = skia.Paint()
        self._post_paint.setBlendMode(skia.BlendMode.kSrc)

    def _frame_background_color(self) -> skia.Color4f:
        """Opaque job background — Skia effects (glow, blur) must composite on solid pixels.

        A transparent root canvas makes soft halos look correct in PNG viewers that
        composite alpha, but dull/wrong in H.264 (no alpha). Clearing to the theme
        background matches video export to preview snapshots.
        """
        bg = resolve_color(ColorToken.BACKGROUND, self._job_info.colors)
        r, g, b, _a = bg.rgba
        return skia.Color4f(r, g, b, 1.0)

    @property
    def needs_gl(self) -> bool:
        return self._needs_gl

    def _ensure_gl_ctx(self) -> GLContext:
        if self._gl_ctx is None:
            self._gl_ctx = GLContext(self._job_info.width, self._job_info.height)
            self._needs_gl = True
        return self._gl_ctx

    def release_gl_context(self) -> None:
        """Release only the shared GL context (preview GL-context-only reprepare)."""
        if self._gl_ctx is not None:
            with suppress(Exception):
                self._gl_ctx.release()
            self._gl_ctx = None

    def release_worker_resources(self) -> None:
        """Best-effort teardown in worker processes (PyAV, GL) so children join promptly."""
        for track in self._tracks:
            for el in track.clips:
                closer = getattr(el, "close_av_container", None)
                if callable(closer):
                    with suppress(Exception):
                        closer()
        self.release_gl_context()

    def composite(self, time: TimeState) -> skia.Surface:
        canvas = self._surface.getCanvas()
        canvas.clear(self._frame_background_color())

        for track in self._tracks:
            if not track.enabled:
                continue

            in_p, out_p = self._transition_progress(track, time.t)
            visibility = in_p * (1.0 - out_p)

            if visibility <= 0.0:
                continue

            active_trans, progress, is_intro = self._active_transition(track, time.t, in_p, out_p)

            t0 = _time.perf_counter()
            if active_trans and active_trans.type == TransitionType.BLUR:
                self._render_track_with_blur(track, time, canvas, active_trans, progress, is_intro)
            elif active_trans:
                self._apply_transition_pre(canvas, active_trans, progress, is_intro)
                self._render_track(track, time, canvas)
                canvas.restore()
            else:
                self._render_track(track, time, canvas)
            elapsed = _time.perf_counter() - t0
            self._track_times[track.id] = self._track_times.get(track.id, 0.0) + elapsed

        self._frames_composited += 1
        if self._timing_log_every > 0 and self._frames_composited % self._timing_log_every == 0:
            n = self._frames_composited
            parts = ", ".join(
                f"{tid}={(total / n) * 1000:.1f}ms"
                for tid, total in sorted(
                    self._track_times.items(), key=lambda kv: kv[1], reverse=True
                )
            )
            self._log.info("pid=%d frames=%d avg/track: %s", os.getpid(), n, parts)

        return self._surface

    def render(
        self,
        writer: VideoWriter,
        total_frames: int,
        *,
        cancel: threading.Event | None = None,
        progress: RenderProgress | None = None,
    ) -> int:
        """Run the full frame loop. Returns number of frames written."""
        written = 0
        for frame in range(total_frames):
            if cancel and cancel.is_set():
                break
            surface = self.composite(TimeState(frame=frame, t=frame / self._job_info.fps))
            writer.write_frame(surface)
            written += 1
            if progress:
                progress(written, total_frames)
        return written

    # ── Transition progress ──────────────────────────────────────────────────

    def _transition_progress(self, track: TrackClip, t: float) -> tuple[float, float]:
        """Returns (in_progress, out_progress) each in 0.0..1.0.
        in_progress:  0 = fully hidden, 1 = fully visible (intro done)
        out_progress: 0 = fully visible, 1 = fully hidden (outro done)
        """
        in_p = 1.0
        out_p = 0.0

        if track.transition_in:
            end = track.start + track.transition_in.duration
            if t < end:
                raw = (t - track.start) / track.transition_in.duration
                in_p = apply_easing(track.transition_in.easing, raw)

        if track.transition_out:
            assert track.duration is not None
            out_start = track.start + track.duration - track.transition_out.duration
            if t > out_start:
                raw = (t - out_start) / track.transition_out.duration
                out_p = apply_easing(track.transition_out.easing, raw)

        return in_p, out_p

    def _active_transition(
        self,
        track: TrackClip,
        t: float,
        in_p: float,
        out_p: float,
    ) -> tuple[TrackTransition | None, float, bool]:
        """Returns (active_transition, eased_progress, is_intro).
        progress: 0 = fully visible, 1 = fully hidden.
        """
        if track.transition_out and out_p > 0.0:
            return track.transition_out, out_p, False
        if track.transition_in and in_p < 1.0:
            return track.transition_in, 1.0 - in_p, True
        return None, 0.0, True

    # ── Canvas-based transitions (no offscreen) ─────────────────────────────

    def _apply_transition_pre(
        self,
        canvas: skia.Canvas,
        trans: TrackTransition,
        progress: float,
        is_intro: bool,
    ) -> None:
        """Save canvas state and apply transition. Caller must canvas.restore()."""
        w = float(self._job_info.width)
        h = float(self._job_info.height)

        match trans.type:
            case TransitionType.FADE:
                alpha = int((1.0 - progress) * 255)
                rect = skia.Rect.MakeWH(w, h)
                canvas.saveLayerAlpha(rect, alpha)

            case TransitionType.SLIDE:
                canvas.save()
                dx_m, dy_m = _DIR_VECTORS.get(trans.direction, (-1.0, 0.0))
                canvas.translate(dx_m * progress * w, dy_m * progress * h)

            case TransitionType.SCALE:
                canvas.save()
                s = 1.0 - progress
                canvas.translate(w * 0.5, h * 0.5)
                canvas.scale(s, s)
                canvas.translate(-w * 0.5, -h * 0.5)

            case TransitionType.WIPE:
                canvas.save()
                dx_m, dy_m = _DIR_VECTORS.get(trans.direction, (-1.0, 0.0))
                visible = 1.0 - progress
                if abs(dx_m) > 0:
                    clip_w = w * visible
                    x = 0.0 if dx_m < 0 else w - clip_w
                    canvas.clipRect(skia.Rect.MakeXYWH(x, 0, clip_w, h))
                else:
                    clip_h = h * visible
                    y = 0.0 if dy_m < 0 else h - clip_h
                    canvas.clipRect(skia.Rect.MakeXYWH(0, y, w, clip_h))

            case _:
                canvas.save()

    # ── Blur transition (needs offscreen surface) ────────────────────────────

    def _get_blur_surface(self) -> skia.Surface:
        if self._blur_surface is None:
            self._blur_surface = skia.Surface(self._job_info.width, self._job_info.height)
        return self._blur_surface

    def _render_track_with_blur(
        self,
        track: TrackClip,
        time: TimeState,
        canvas: skia.Canvas,
        trans: TrackTransition,
        progress: float,
        is_intro: bool,
    ) -> None:
        blur_surf = self._get_blur_surface()
        blur_canvas = blur_surf.getCanvas()
        blur_canvas.clear(skia.ColorTRANSPARENT)

        if isinstance(track, (GLTrack, GLEffectTrack)):
            self._render_gl_family_track(track, time, blur_canvas)
        else:
            self._render_skia_track(track, time, blur_canvas)

        sigma = progress * 20.0
        image = blur_surf.makeImageSnapshot()
        paint = skia.Paint()
        if sigma > 0.1:
            paint.setImageFilter(skia.ImageFilters.Blur(sigma, sigma))
        paint.setAlphaf(1.0 - progress)
        canvas.drawImage(image, 0, 0, paint=paint)

    # ── Audio resolution ─────────────────────────────────────────────────────

    def _resolve_audio_for(self, clip: VisualClip, frame: int) -> AudioBusFrame:
        """Look up the AudioBusFrame for this clip/frame; zero if N/A.

        Returns a zero frame for non-audio clips so callers can pass it to
        RenderContext unconditionally without per-clip branching.
        """
        if isinstance(clip, AudioVisualMixin):
            return resolve_audio_bus_frame_for_clip(
                audio=self._audio,
                bus_select=clip.bus_select,
                frame=frame,
            )
        return AudioBusFrame.zero()

    # ── Track rendering dispatch ─────────────────────────────────────────────

    def _render_track(self, track: TrackClip, time: TimeState, canvas: skia.Canvas) -> None:
        if isinstance(track, (GLTrack, GLEffectTrack)):
            self._render_gl_family_track(track, time, canvas)
        else:
            self._render_skia_track(track, time, canvas)

    def _render_gl_family_track(
        self, track: GLTrack | GLEffectTrack, time: TimeState, canvas: skia.Canvas
    ) -> None:
        if isinstance(track, GLEffectTrack):
            self._render_gleffect_track(track, time, canvas)
        else:
            self._render_gl_track(track, time, canvas)

    def _render_skia_track(self, track: TrackClip, time: TimeState, canvas: skia.Canvas) -> None:
        if track_needs_effect_pipeline(track, self._for_preview):
            gl_ctx = self._ensure_gl_ctx()
            render_track_with_track_effects(
                track=track,
                canvas=canvas,
                job_info=self._job_info,
                time=time,
                audio=self._audio,
                for_preview=self._for_preview,
                gl_ctx=gl_ctx,
                resolve_audio=self._resolve_audio_for,
            )
            return

        for i, clip in enumerate(track.clips):
            if not isinstance(clip, VisualClip) or not clip.enabled:
                continue
            assert clip.duration is not None
            if time.t < clip.start or time.t >= clip.start + clip.duration:
                continue
            bounds = track._rects[i] if track._rects else self._track_rect
            audio = self._resolve_audio_for(clip, time.frame)
            if visual_clip_needs_effect_pipeline(clip, self._for_preview):
                gl_ctx = None
                if chain_backend_for_clip(clip) == "gl":
                    gl_ctx = self._ensure_gl_ctx()
                render_skia_clip_with_effects(
                    clip=clip,
                    bounds=bounds,
                    canvas=canvas,
                    job_info=self._job_info,
                    time=time,
                    audio=self._audio,
                    audio_bus_frame=audio,
                    for_preview=self._for_preview,
                    gl_ctx=gl_ctx,
                )
                continue
            ctx = RenderContext(
                job=self._job_info,
                time=time,
                bounds=bounds,
                canvas=canvas,
                audio_bus_frame=audio,
                log=self._log,
            )
            clip.draw(ctx)

    def _render_gl_track(self, track: GLTrack, time: TimeState, canvas: skia.Canvas) -> None:
        if track_needs_effect_pipeline(track, self._for_preview):
            gl_ctx = self._ensure_gl_ctx()
            render_track_with_track_effects(
                track=track,
                canvas=canvas,
                job_info=self._job_info,
                time=time,
                audio=self._audio,
                for_preview=self._for_preview,
                gl_ctx=gl_ctx,
                resolve_audio=self._resolve_audio_for,
            )
            return

        gl = self._ensure_gl_ctx()
        gl_fbo_dirty = False

        for i, clip in enumerate(track.clips):
            if not isinstance(clip, VisualClip) or not clip.enabled:
                continue
            assert clip.duration is not None
            if time.t < clip.start or time.t >= clip.start + clip.duration:
                continue
            bounds = track._rects[i] if track._rects else self._track_rect
            audio = self._resolve_audio_for(clip, time.frame)
            if visual_clip_needs_effect_pipeline(clip, self._for_preview):
                if gl_fbo_dirty:
                    canvas.drawBitmap(gl.to_skia_bitmap(), 0, 0)
                    gl.clear()
                    gl_fbo_dirty = False
                render_gl_clip_with_effects(
                    clip=clip,
                    bounds=bounds,
                    canvas=canvas,
                    gl_ctx=gl,
                    job_info=self._job_info,
                    time=time,
                    audio=self._audio,
                    audio_bus_frame=audio,
                    for_preview=self._for_preview,
                )
                continue
            if not gl_fbo_dirty:
                gl.clear()
                gl.fbo.use()
            gl.reset_clip_state()
            ctx = RenderContext(
                job=self._job_info,
                time=time,
                bounds=bounds,
                canvas=gl.ctx,
                source_texture=None,
                audio_bus_frame=audio,
                log=self._log,
            )
            clip.draw(ctx)
            gl_fbo_dirty = True

        if gl_fbo_dirty:
            canvas.drawBitmap(gl.to_skia_bitmap(), 0, 0)

    def _render_gleffect_track(
        self, track: GLEffectTrack, time: TimeState, canvas: skia.Canvas
    ) -> None:
        assert self._gl_ctx is not None

        active: list[tuple[int, VisualClip]] = []
        for i, clip in enumerate(track.clips):
            if not isinstance(clip, VisualClip) or not clip.enabled:
                continue
            assert clip.duration is not None
            if time.t < clip.start or time.t >= clip.start + clip.duration:
                continue
            active.append((i, clip))

        if not active:
            return

        gl = self._gl_ctx
        gl.clear()
        gl.fbo.use()

        post_process_nodes = [e for _, e in active if isinstance(e, GLPostProcessClip)]
        source_texture = gl.upload_skia_surface(self._surface) if post_process_nodes else None

        try:
            for i, clip in active:
                bounds = track._rects[i] if track._rects else self._track_rect
                gl.reset_clip_state()
                ctx = RenderContext(
                    job=self._job_info,
                    time=time,
                    bounds=bounds,
                    canvas=gl.ctx,  # moderngl.Context
                    source_texture=source_texture,
                    audio_bus_frame=self._resolve_audio_for(clip, time.frame),
                    log=self._log,
                )
                clip.draw(ctx)
        finally:
            if source_texture is not None:
                source_texture.release()

        canvas.drawBitmap(gl.to_skia_bitmap(), 0, 0, self._post_paint)
