"""Per-clip effect chain execution (bounds-local, homogeneous backends)."""

from __future__ import annotations

import logging
import math
from contextlib import suppress
from typing import TYPE_CHECKING

import moderngl
import numpy as np
import skia

from pixfabrica_core.audio.bus import AudioBusFrame, AudioTimeline
from pixfabrica_core.clips import Clip, JobInfo, RenderContext, TimeState, VisualClip
from pixfabrica_core.composition.effect_def import (
    EffectContext,
    EffectInstance,
    GLEffect,
    RasterEffect,
    SkiaEffect,
    clip_has_enabled_effects,
    enabled_effects,
    resolve_effect_audio_bus_frame,
    track_gl_overscan_fraction,
    track_has_enabled_effects,
)
from pixfabrica_core.graphics import Rect
from pixfabrica_core.job_effects import chain_backend_for_clip, chain_backend_for_track
from pixfabrica_renderer.gl_context import GLContext

if TYPE_CHECKING:
    from pixfabrica_core.composition.track import TrackClip

_log = logging.getLogger("pixfabrica.effects")


def _iw(bounds: Rect) -> int:
    return max(1, int(round(bounds.width)))


def _ih(bounds: Rect) -> int:
    return max(1, int(round(bounds.height)))


def _overscan_pad(w: int, h: int, margin: float) -> tuple[int, int, float]:
    if margin <= 0.0:
        return 0, 0, 0.0
    pad_x = int(math.ceil(w * margin - 1e-9))
    pad_y = int(math.ceil(h * margin - 1e-9))
    overscan = max(pad_x / w, pad_y / h)
    return pad_x, pad_y, overscan


def _local_bounds(bounds: Rect) -> Rect:
    return Rect(0, 0, bounds.width, bounds.height)


def _skia_surface(w: int, h: int) -> skia.Surface:
    """Premul-alpha offscreen target — required for partial-opacity clips (e.g. sweep lines)."""
    info = skia.ImageInfo.MakeN32Premul(max(1, w), max(1, h))
    surface = skia.Surface(info)
    if surface is None:
        raise RuntimeError(f"failed to allocate Skia surface {w}x{h}")
    return surface


def _upload_surface_to_texture(gl: moderngl.Context, surface: skia.Surface) -> moderngl.Texture:
    surface.getCanvas().flush()
    image = surface.makeImageSnapshot()
    row_bytes = image.width() * 4
    buf = bytearray(image.height() * row_bytes)
    image.readPixels(skia.ImageInfo.MakeN32Premul(image.width(), image.height()), buf, row_bytes)
    arr = np.frombuffer(buf, dtype=np.uint8).reshape(image.height(), image.width(), 4)
    arr = np.flipud(arr).copy()
    arr[:, :, [0, 2]] = arr[:, :, [2, 0]]
    texture = gl.texture((image.width(), image.height()), 4, arr.tobytes())
    texture.filter = (moderngl.LINEAR, moderngl.LINEAR)
    texture.repeat_x = False
    texture.repeat_y = False
    return texture


def _texture_to_skia_surface(texture: moderngl.Texture) -> skia.Surface:
    w, h = texture.size
    raw = np.frombuffer(texture.read(), dtype=np.uint8).reshape(h, w, 4)
    raw = np.flipud(raw).copy()
    raw[:, :, [0, 2]] = raw[:, :, [2, 0]]
    a = raw[:, :, 3:4].astype(np.float32) / 255.0
    raw[:, :, :3] = (raw[:, :, :3].astype(np.float32) * a).astype(np.uint8)
    # installPixels holds a pointer, not a copy — keep bytes on the surface.
    pixel_buf = raw.tobytes()
    bitmap = skia.Bitmap()
    bitmap.installPixels(
        skia.ImageInfo.MakeN32Premul(w, h),
        pixel_buf,
        w * 4,
    )
    surface = _skia_surface(w, h)
    surface.getCanvas().drawBitmap(bitmap, 0, 0)
    return surface


class _BoundsGL:
    """Transient bounds-sized GL ping-pong targets."""

    def __init__(self, gl_ctx: GLContext, w: int, h: int) -> None:
        self._parent = gl_ctx
        self._ctx = gl_ctx.ctx
        self._w = w
        self._h = h
        self._owns_resources = False
        if w == gl_ctx._width and h == gl_ctx._height:
            self._tex_a = gl_ctx._color_tex
            self._tex_b = gl_ctx._ping_tex
            self._fbo_a = gl_ctx._fbo
            self._fbo_b = gl_ctx._ping_fbo
        else:
            self._owns_resources = True
            self._tex_a = self._ctx.texture((w, h), 4)
            self._tex_b = self._ctx.texture((w, h), 4)
            self._fbo_a = self._ctx.framebuffer(color_attachments=[self._tex_a])
            self._fbo_b = self._ctx.framebuffer(color_attachments=[self._tex_b])

    def release(self) -> None:
        if not self._owns_resources:
            return
        for obj in (self._fbo_a, self._fbo_b, self._tex_a, self._tex_b):
            with suppress(Exception):
                obj.release()

    def clear_draw_target(self) -> None:
        self._fbo_a.use()
        self._ctx.clear(0.0, 0.0, 0.0, 0.0)

    @property
    def draw_fbo(self) -> moderngl.Framebuffer:
        return self._fbo_a

    @property
    def draw_ctx(self) -> moderngl.Context:
        return self._ctx

    def texture_from_skia(self, surface: skia.Surface) -> moderngl.Texture:
        return _upload_surface_to_texture(self._ctx, surface)

    def run_gl_chain(
        self,
        *,
        effects: list[EffectInstance],
        parent: Clip | None,
        initial: moderngl.Texture,
        job_info: JobInfo,
        time: TimeState,
        bounds: Rect,
        audio: AudioTimeline,
        audio_bus_frame: AudioBusFrame,
        for_preview: bool,
        src_uv_scale: tuple[float, float] = (1.0, 1.0),
        src_uv_bias: tuple[float, float] = (0.0, 0.0),
    ) -> moderngl.Texture:
        read_tex = initial
        write_fbo = self._fbo_b
        write_tex = self._tex_b
        first_pass = True
        for fx in enabled_effects(effects):
            if for_preview and type(fx).skip_in_preview:
                continue
            if not isinstance(fx, GLEffect):
                continue
            write_fbo.use()
            self._ctx.clear(0.0, 0.0, 0.0, 0.0)
            fx_audio = resolve_effect_audio_bus_frame(
                audio,
                parent,
                fx,
                time.frame,
                parent_frame=audio_bus_frame,
            )
            pass_scale = src_uv_scale if first_pass else (1.0, 1.0)
            pass_bias = src_uv_bias if first_pass else (0.0, 0.0)
            ctx = EffectContext(
                job=job_info,
                time=time,
                bounds=_local_bounds(bounds),
                source=read_tex,
                target=write_fbo,
                audio_bus_frame=fx_audio,
                src_uv_scale=pass_scale,
                src_uv_bias=pass_bias,
                log=_log,
            )
            fx.apply(ctx)
            read_tex = write_tex
            first_pass = False
            if write_fbo is self._fbo_b:
                write_fbo, write_tex = self._fbo_a, self._tex_a
            else:
                write_fbo, write_tex = self._fbo_b, self._tex_b
        return read_tex


def run_skia_effect_chain(
    *,
    clip: VisualClip,
    surface: skia.Surface,
    job_info: JobInfo,
    time: TimeState,
    bounds: Rect,
    audio: AudioTimeline,
    audio_bus_frame: AudioBusFrame,
    for_preview: bool,
) -> skia.Surface:
    w, h = surface.width(), surface.height()
    source = surface
    target = _skia_surface(w, h)
    for fx in enabled_effects(clip.effects):
        if for_preview and type(fx).skip_in_preview:
            continue
        if not isinstance(fx, SkiaEffect):
            continue
        target.getCanvas().clear(skia.ColorTRANSPARENT)
        fx_audio = resolve_effect_audio_bus_frame(
            audio,
            clip,
            fx,
            time.frame,
            parent_frame=audio_bus_frame,
        )
        ctx = EffectContext(
            job=job_info,
            time=time,
            bounds=_local_bounds(bounds),
            source=source,
            target=target,
            audio_bus_frame=fx_audio,
            log=_log,
        )
        fx.apply(ctx)
        source, target = target, source
    return source


def run_raster_effect_chain(
    *,
    clip: VisualClip,
    surface: skia.Surface,
    job_info: JobInfo,
    time: TimeState,
    bounds: Rect,
    audio: AudioTimeline,
    audio_bus_frame: AudioBusFrame,
    for_preview: bool,
) -> skia.Surface:
    if for_preview:
        return surface
    source = surface
    w, h = surface.width(), surface.height()
    target = _skia_surface(w, h)
    for fx in enabled_effects(clip.effects):
        if not isinstance(fx, RasterEffect):
            continue
        target.getCanvas().clear(skia.ColorTRANSPARENT)
        fx_audio = resolve_effect_audio_bus_frame(
            audio,
            clip,
            fx,
            time.frame,
            parent_frame=audio_bus_frame,
        )
        ctx = EffectContext(
            job=job_info,
            time=time,
            bounds=_local_bounds(bounds),
            source=source,
            target=target,
            audio_bus_frame=fx_audio,
            log=_log,
        )
        fx.apply(ctx)
        source, target = target, source
    return source


def composite_skia_surface_to_canvas(
    canvas: skia.Canvas, surface: skia.Surface, bounds: Rect
) -> None:
    canvas.drawImage(surface.makeImageSnapshot(), bounds.x, bounds.y)


def render_skia_clip_with_effects(
    *,
    clip: VisualClip,
    bounds: Rect,
    canvas: skia.Canvas,
    job_info: JobInfo,
    time: TimeState,
    audio: AudioTimeline,
    audio_bus_frame: AudioBusFrame,
    for_preview: bool,
    gl_ctx: GLContext | None = None,
    overscan: float = 0.0,
) -> None:
    w, h = _iw(bounds), _ih(bounds)
    local = _local_bounds(bounds)
    chain = chain_backend_for_clip(clip)

    if chain is None:
        ctx = RenderContext(
            job=job_info,
            time=time,
            bounds=local,
            canvas=canvas,
            audio_bus_frame=audio_bus_frame,
            overscan=overscan,
            log=_log,
        )
        canvas.save()
        canvas.translate(bounds.x, bounds.y)
        clip.draw(ctx)
        canvas.restore()
        return

    offscreen = _skia_surface(w, h)
    off_canvas = offscreen.getCanvas()
    off_canvas.clear(skia.ColorTRANSPARENT)
    draw_ctx = RenderContext(
        job=job_info,
        time=time,
        bounds=local,
        canvas=off_canvas,
        audio_bus_frame=audio_bus_frame,
        overscan=overscan,
        log=_log,
    )
    clip.draw(draw_ctx)

    if chain == "skia":
        result = run_skia_effect_chain(
            clip=clip,
            surface=offscreen,
            job_info=job_info,
            time=time,
            bounds=bounds,
            audio=audio,
            audio_bus_frame=audio_bus_frame,
            for_preview=for_preview,
        )
        composite_skia_surface_to_canvas(canvas, result, bounds)
        return

    if chain == "raster":
        result = run_raster_effect_chain(
            clip=clip,
            surface=offscreen,
            job_info=job_info,
            time=time,
            bounds=bounds,
            audio=audio,
            audio_bus_frame=audio_bus_frame,
            for_preview=for_preview,
        )
        composite_skia_surface_to_canvas(canvas, result, bounds)
        return

    if chain == "gl":
        if gl_ctx is None:
            raise RuntimeError("GL effect chain on Skia clip requires GLContext")
        render_skia_parent_gl_chain(
            clip=clip,
            bounds=bounds,
            canvas=canvas,
            gl_ctx=gl_ctx,
            job_info=job_info,
            time=time,
            audio=audio,
            audio_bus_frame=audio_bus_frame,
            for_preview=for_preview,
        )
        return


def render_skia_parent_gl_chain(
    *,
    clip: VisualClip,
    bounds: Rect,
    canvas: skia.Canvas,
    gl_ctx: GLContext,
    job_info: JobInfo,
    time: TimeState,
    audio: AudioTimeline,
    audio_bus_frame: AudioBusFrame,
    for_preview: bool,
) -> None:
    w, h = _iw(bounds), _ih(bounds)
    local = _local_bounds(bounds)
    offscreen = _skia_surface(w, h)
    off_canvas = offscreen.getCanvas()
    off_canvas.clear(skia.ColorTRANSPARENT)
    draw_ctx = RenderContext(
        job=job_info,
        time=time,
        bounds=local,
        canvas=off_canvas,
        audio_bus_frame=audio_bus_frame,
        log=_log,
    )
    clip.draw(draw_ctx)

    bounds_gl = _BoundsGL(gl_ctx, w, h)
    try:
        tex = bounds_gl.texture_from_skia(offscreen)
        try:
            out_tex = bounds_gl.run_gl_chain(
                effects=clip.effects,
                parent=clip,
                initial=tex,
                job_info=job_info,
                time=time,
                bounds=bounds,
                audio=audio,
                audio_bus_frame=audio_bus_frame,
                for_preview=for_preview,
            )
            result = _texture_to_skia_surface(out_tex)
            composite_skia_surface_to_canvas(canvas, result, bounds)
        finally:
            tex.release()
    finally:
        bounds_gl.release()


def render_gl_clip_with_effects(
    *,
    clip: VisualClip,
    bounds: Rect,
    canvas: skia.Canvas,
    gl_ctx: GLContext,
    job_info: JobInfo,
    time: TimeState,
    audio: AudioTimeline,
    audio_bus_frame: AudioBusFrame,
    for_preview: bool,
    overscan: float = 0.0,
) -> None:
    w, h = _iw(bounds), _ih(bounds)
    local = _local_bounds(bounds)
    chain = chain_backend_for_clip(clip)
    bounds_gl = _BoundsGL(gl_ctx, w, h)
    try:
        bounds_gl.clear_draw_target()
        draw_ctx = RenderContext(
            job=job_info,
            time=time,
            bounds=local,
            canvas=bounds_gl.draw_ctx,
            audio_bus_frame=audio_bus_frame,
            overscan=overscan,
            log=_log,
        )
        bounds_gl.draw_fbo.use()
        clip.draw(draw_ctx)

        if chain == "gl":
            out_tex = bounds_gl.run_gl_chain(
                effects=clip.effects,
                parent=clip,
                initial=bounds_gl._tex_a,
                job_info=job_info,
                time=time,
                bounds=bounds,
                audio=audio,
                audio_bus_frame=audio_bus_frame,
                for_preview=for_preview,
            )
            result = _texture_to_skia_surface(out_tex)
            composite_skia_surface_to_canvas(canvas, result, bounds)
            return

        if chain == "skia":
            skia_surface = _texture_to_skia_surface(bounds_gl._tex_a)
            result = run_skia_effect_chain(
                clip=clip,
                surface=skia_surface,
                job_info=job_info,
                time=time,
                bounds=bounds,
                audio=audio,
                audio_bus_frame=audio_bus_frame,
                for_preview=for_preview,
            )
            composite_skia_surface_to_canvas(canvas, result, bounds)
            return

        if chain == "raster":
            skia_surface = _texture_to_skia_surface(bounds_gl._tex_a)
            result = run_raster_effect_chain(
                clip=clip,
                surface=skia_surface,
                job_info=job_info,
                time=time,
                bounds=bounds,
                audio=audio,
                audio_bus_frame=audio_bus_frame,
                for_preview=for_preview,
            )
            composite_skia_surface_to_canvas(canvas, result, bounds)
    finally:
        bounds_gl.release()


def visual_clip_needs_effect_pipeline(clip: VisualClip, for_preview: bool) -> bool:
    if not clip_has_enabled_effects(clip.effects):
        return False
    if not for_preview:
        return True
    return any(
        not (for_preview and type(fx).skip_in_preview) for fx in enabled_effects(clip.effects)
    )


def track_needs_effect_pipeline(track: TrackClip, for_preview: bool) -> bool:
    if not track_has_enabled_effects(track.effects):
        return False
    if chain_backend_for_track(track) != "gl":
        return False
    if not for_preview:
        return True
    return any(
        not (for_preview and type(fx).skip_in_preview) for fx in enabled_effects(track.effects)
    )


def render_gl_visual_to_canvas(
    *,
    clip: VisualClip,
    bounds: Rect,
    canvas: skia.Canvas,
    gl_ctx: GLContext,
    job_info: JobInfo,
    time: TimeState,
    audio: AudioTimeline,
    audio_bus_frame: AudioBusFrame,
    for_preview: bool,
    overscan: float = 0.0,
) -> None:
    if visual_clip_needs_effect_pipeline(clip, for_preview):
        render_gl_clip_with_effects(
            clip=clip,
            bounds=bounds,
            canvas=canvas,
            gl_ctx=gl_ctx,
            job_info=job_info,
            time=time,
            audio=audio,
            audio_bus_frame=audio_bus_frame,
            for_preview=for_preview,
            overscan=overscan,
        )
        return

    w, h = _iw(bounds), _ih(bounds)
    local = _local_bounds(bounds)
    bounds_gl = _BoundsGL(gl_ctx, w, h)
    try:
        bounds_gl.clear_draw_target()
        draw_ctx = RenderContext(
            job=job_info,
            time=time,
            bounds=local,
            canvas=bounds_gl.draw_ctx,
            audio_bus_frame=audio_bus_frame,
            overscan=overscan,
            log=_log,
        )
        bounds_gl.draw_fbo.use()
        clip.draw(draw_ctx)
        result = _texture_to_skia_surface(bounds_gl._tex_a)
        composite_skia_surface_to_canvas(canvas, result, bounds)
    finally:
        bounds_gl.release()


def _render_active_track_clips(
    *,
    track: TrackClip,
    canvas: skia.Canvas,
    job_info: JobInfo,
    time: TimeState,
    audio: AudioTimeline,
    for_preview: bool,
    gl_ctx: GLContext | None,
    resolve_audio,
    overscan: float = 0.0,
) -> None:
    track_rect = Rect(0, 0, job_info.width, job_info.height)
    for i, clip in enumerate(track.clips):
        if not isinstance(clip, VisualClip) or not _clip_active_at(clip, time):
            continue
        bounds = track._rects[i] if track._rects else track_rect
        audio_bus_frame = resolve_audio(clip, time.frame)
        backend = getattr(clip, "backend", "")
        if backend == "gl":
            if gl_ctx is None:
                raise RuntimeError("GL clip on track requires GLContext")
            render_gl_visual_to_canvas(
                clip=clip,
                bounds=bounds,
                canvas=canvas,
                gl_ctx=gl_ctx,
                job_info=job_info,
                time=time,
                audio=audio,
                audio_bus_frame=audio_bus_frame,
                for_preview=for_preview,
                overscan=overscan,
            )
            continue
        if visual_clip_needs_effect_pipeline(clip, for_preview):
            render_skia_clip_with_effects(
                clip=clip,
                bounds=bounds,
                canvas=canvas,
                job_info=job_info,
                time=time,
                audio=audio,
                audio_bus_frame=audio_bus_frame,
                for_preview=for_preview,
                gl_ctx=gl_ctx,
                overscan=overscan,
            )
            continue
        local = _local_bounds(bounds)
        ctx = RenderContext(
            job=job_info,
            time=time,
            bounds=local,
            canvas=canvas,
            audio_bus_frame=audio_bus_frame,
            overscan=overscan,
            log=_log,
        )
        canvas.save()
        canvas.translate(bounds.x, bounds.y)
        clip.draw(ctx)
        canvas.restore()


def _clip_active_at(clip: VisualClip, time: TimeState) -> bool:
    if not clip.enabled:
        return False
    assert clip.duration is not None
    return clip.start <= time.t < clip.start + clip.duration


def render_track_with_track_effects(
    *,
    track: TrackClip,
    canvas: skia.Canvas,
    job_info: JobInfo,
    time: TimeState,
    audio: AudioTimeline,
    for_preview: bool,
    gl_ctx: GLContext,
    resolve_audio,
) -> None:
    track_bounds = Rect(0, 0, job_info.width, job_info.height)
    w, h = _iw(track_bounds), _ih(track_bounds)
    margin = track_gl_overscan_fraction(track.effects)
    pad_x, pad_y, overscan = _overscan_pad(w, h, margin)
    off_w, off_h = w + 2 * pad_x, h + 2 * pad_y

    offscreen = _skia_surface(off_w, off_h)
    off_canvas = offscreen.getCanvas()
    off_canvas.clear(skia.ColorTRANSPARENT)
    off_canvas.save()
    off_canvas.translate(float(pad_x), float(pad_y))
    _render_active_track_clips(
        track=track,
        canvas=off_canvas,
        job_info=job_info,
        time=time,
        audio=audio,
        for_preview=for_preview,
        gl_ctx=gl_ctx,
        resolve_audio=resolve_audio,
        overscan=overscan,
    )
    off_canvas.restore()

    src_uv_scale = (w / off_w, h / off_h)
    src_uv_bias = (pad_x / off_w, pad_y / off_h)
    bounds_gl = _BoundsGL(gl_ctx, w, h)
    try:
        tex = bounds_gl.texture_from_skia(offscreen)
        try:
            out_tex = bounds_gl.run_gl_chain(
                effects=track.effects,
                parent=track,
                initial=tex,
                job_info=job_info,
                time=time,
                bounds=track_bounds,
                audio=audio,
                audio_bus_frame=AudioBusFrame.zero(),
                for_preview=for_preview,
                src_uv_scale=src_uv_scale,
                src_uv_bias=src_uv_bias,
            )
            result = _texture_to_skia_surface(out_tex)
            composite_skia_surface_to_canvas(canvas, result, track_bounds)
        finally:
            tex.release()
    finally:
        bounds_gl.release()
