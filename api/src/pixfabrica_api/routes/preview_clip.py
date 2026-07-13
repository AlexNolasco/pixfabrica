"""WebSocket endpoint for isolated timeline clip preview.

WS /preview/clip

Client sends JSON with clip payload + job theme slice + local time ``t``.
Server caches prepared compositor by content fingerprint and returns RGBA frames.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import struct
from dataclasses import dataclass
from typing import Any

import skia
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from pixfabrica_api.catalog_cache import get_catalog_cache
from pixfabrica_api.demo_audio import demo_timeline_for_bus
from pixfabrica_api.plugin_registry import ensure_plugins_registered
from pixfabrica_api.preview_runtime import (
    prepare_clip_compositor,
    release_compositor,
    render_preview_frame,
    typography_for_preview_surface,
)
from pixfabrica_api.preview_runtime import (
    skia_surface_rgba_bytes as _skia_surface_rgba_bytes,
)
from pixfabrica_api.preview_samples import list_preview_sample_ids, preview_timeline_for_bus
from pixfabrica_api.server_config import DEFAULT_LOCALE, MAX_PREVIEW_LONG_SIDE
from pixfabrica_core.audio.preview_prepare import bus_names_needed_for_clip
from pixfabrica_core.clips import JobInfo, VisualClip
from pixfabrica_core.composition.registry import deserialize_clip
from pixfabrica_core.composition.track import FillLayout, GLTrack, SkiaTrack
from pixfabrica_core.composition.unknown import UnknownClip
from pixfabrica_core.fonts.skia_resolver import warmup_typography_palette
from pixfabrica_core.prepare_diagnostics import (
    PrepareDiagnostics,
    PrepareWarning,
    prepare_warnings_event,
)
from pixfabrica_core.preview_dims import (
    DEFAULT_REFERENCE_HEIGHT,
    preview_dimensions,
    scale_typography_for_job_height,
)
from pixfabrica_core.project_variables import apply_project_variables_to_clip
from pixfabrica_core.theme.color import ColorPalette
from pixfabrica_core.theme.typography import FontPalette
from pixfabrica_renderer.compositor import Compositor

log = logging.getLogger("pixfabrica.api.preview_clip")

router = APIRouter(tags=["preview"])

_MAX_LOOP_SECONDS = 120.0
_TRACK_NODE_TYPES = {
    "skia": "std-skia-track",
    "gl": "std-gl-track",
}


def _preview_clip_payload(msg: dict[str, Any]) -> dict[str, Any]:
    raw = msg.get("clip")
    if isinstance(raw, dict):
        return raw
    raise ValueError("clip object required")


def _fingerprint(msg: dict[str, Any], preview_w: int, preview_h: int) -> str:
    payload = {
        "clip": msg.get("clip"),
        "colors": msg.get("colors"),
        "typography": msg.get("typography"),
        "locale": msg.get("locale", DEFAULT_LOCALE),
        "track_kind": msg.get("track_kind"),
        "title": msg.get("title"),
        "author": msg.get("author"),
        "job_height": msg.get("height"),
        "reference_height": msg.get("reference_height"),
        "preview_w": preview_w,
        "preview_h": preview_h,
        "fps": msg.get("fps"),
        "loop_seconds": msg.get("loop_seconds"),
        "preview_sample": msg.get("preview_sample"),
        "preview_bus_muted": msg.get("preview_bus_muted"),
    }
    return hashlib.md5(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _clamp_loop_seconds(raw: Any) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = 8.0
    return max(0.5, min(value, _MAX_LOOP_SECONDS))


async def _send_preview_bytes(websocket: WebSocket, data: bytes) -> None:
    try:
        await websocket.send_bytes(data)
    except WebSocketDisconnect:
        raise


async def _send_preview_text(websocket: WebSocket, text: str) -> None:
    try:
        await websocket.send_text(text)
    except WebSocketDisconnect:
        raise


def _job_info_from_msg(
    msg: dict[str, Any], preview_w: int, preview_h: int, duration: float
) -> JobInfo:
    colors_raw = msg.get("colors") or {}
    typo_raw = msg.get("typography") or {}
    try:
        colors = ColorPalette.model_validate(colors_raw)
    except Exception:
        colors = ColorPalette()
    try:
        typography = FontPalette.model_validate(typo_raw)
    except Exception:
        typography = FontPalette()
    job_height = max(1, int(msg.get("height") or preview_h * 2))
    reference_height = max(1, int(msg.get("reference_height") or DEFAULT_REFERENCE_HEIGHT))
    typography = scale_typography_for_job_height(
        typography,
        job_height=job_height,
        reference_height=reference_height,
    )
    typography = typography_for_preview_surface(
        typography,
        job_height=job_height,
        preview_height=preview_h,
        scale_to_preview=True,
    )
    fps = float(msg.get("fps") or 30.0)
    job_width = max(1, int(msg.get("width") or preview_w))
    return JobInfo(
        title=str(msg.get("title") or "preview"),
        description="",
        width=preview_w,
        height=preview_h,
        fps=fps,
        duration=duration,
        locale=str(msg.get("locale") or DEFAULT_LOCALE),
        colors=colors,
        typography=typography,
        output_width=job_width,
        output_height=job_height,
    )


def _normalize_clip(clip: dict[str, Any], loop_seconds: float) -> dict[str, Any]:
    out = dict(clip)
    out["start"] = 0.0
    out["duration"] = loop_seconds
    return out


def _clip_payload_for_deserialize(clip_data: dict[str, Any], loop_seconds: float) -> dict[str, Any]:
    """Merge catalog defaults under user params (UI may omit fields still at schema defaults)."""
    normalized = _normalize_clip(clip_data, loop_seconds)
    clip_type = str(normalized.get("clip_type") or "")
    detail = get_catalog_cache().details.get(clip_type)
    if not detail:
        return normalized
    return {**detail.defaults, **normalized}


def _build_track(
    track_kind: str,
    clip_data: dict[str, Any],
    loop_seconds: float,
    *,
    title: str,
    author: str,
) -> tuple[SkiaTrack | GLTrack, list[PrepareWarning]]:
    clip = deserialize_clip(_clip_payload_for_deserialize(clip_data, loop_seconds))
    if isinstance(clip, UnknownClip):
        raise ValueError(f"unknown clip type: {clip.raw_clip_type or '<missing>'}")
    if not isinstance(clip, VisualClip):
        raise ValueError(f"clip is not visual: {clip_data.get('clip_type')}")
    variable_warnings = apply_project_variables_to_clip(clip, title=title, author=author)
    if track_kind == "gl":
        track_cls = GLTrack
    elif track_kind == "skia":
        track_cls = SkiaTrack
    else:
        raise ValueError(f"unsupported track_kind: {track_kind}")
    return track_cls(
        id="clip-preview-track",
        start=0.0,
        duration=loop_seconds,
        enabled=True,
        layout=FillLayout(),
        clips=[clip],
    ), variable_warnings


def _preview_audio_for_clip(
    track: SkiaTrack | GLTrack,
    fps: float,
    loop_seconds: float,
    msg: dict[str, Any],
) -> dict[str, list]:
    muted = bool(msg.get("preview_bus_muted"))
    sample_id = msg.get("preview_sample")
    sample_id_str = str(sample_id).strip() if sample_id else None
    if sample_id_str == "":
        sample_id_str = None

    if muted:
        return {}

    buses: set[str] = set()
    for clip in track.clips:
        if isinstance(clip, VisualClip):
            buses |= bus_names_needed_for_clip(clip)

    if not buses:
        return {}

    audio: dict[str, list] = {}
    has_shipped_samples = bool(list_preview_sample_ids())
    for bus in sorted(buses):
        baked = preview_timeline_for_bus(
            bus,
            sample_id=sample_id_str,
            loop_seconds=loop_seconds,
            fps=fps,
            muted=False,
        )
        if baked:
            audio.update(baked)
        elif not has_shipped_samples:
            audio.update(demo_timeline_for_bus(bus, fps))
    return audio


def render_error_frame(width: int, height: int) -> bytes:
    """Skia warning plate for draw()-time failures."""
    surface = skia.Surface(width, height)
    canvas = surface.getCanvas()
    canvas.clear(skia.Color4f(0.07, 0.07, 0.09, 1.0))
    cx = width * 0.5
    cy = height * 0.5
    size = min(width, height) * 0.12
    path = skia.Path()
    path.moveTo(cx, cy - size)
    path.lineTo(cx + size * 0.95, cy + size * 0.85)
    path.lineTo(cx - size * 0.95, cy + size * 0.85)
    path.close()
    fill = skia.Paint(Color=skia.Color4f(0.95, 0.75, 0.1, 1.0), AntiAlias=True)
    canvas.drawPath(path, fill)
    exclamation = skia.Paint(Color=skia.Color4f(0.07, 0.07, 0.09, 1.0), AntiAlias=True)
    font = skia.Font(skia.Typeface("Arial", skia.FontStyle.Bold()), size * 0.9)
    canvas.drawString("!", cx - size * 0.12, cy + size * 0.22, font, exclamation)
    return _skia_surface_rgba_bytes(surface)


@dataclass
class _ClipSession:
    compositor: Compositor
    fingerprint: str
    preview_w: int
    preview_h: int
    fps: float
    loop_seconds: float


async def _prepare_session(
    msg: dict[str, Any],
    preview_w: int,
    preview_h: int,
    loop_seconds: float,
) -> tuple[_ClipSession, PrepareDiagnostics]:
    track_kind = str(msg.get("track_kind") or "skia")
    clip = _preview_clip_payload(msg)

    track, variable_warnings = _build_track(
        track_kind,
        clip,
        loop_seconds,
        title=str(msg.get("title") or "Untitled"),
        author=str(msg.get("author") or ""),
    )
    job_info = _job_info_from_msg(msg, preview_w, preview_h, loop_seconds)
    warmup_typography_palette(job_info.typography)

    preview_audio = _preview_audio_for_clip(track, job_info.fps, loop_seconds, msg)
    compositor, diag = await prepare_clip_compositor(
        track,
        job_info,
        preview_audio,
        variable_warnings=variable_warnings,
    )
    return (
        _ClipSession(
            compositor=compositor,
            fingerprint=_fingerprint(msg, preview_w, preview_h),
            preview_w=preview_w,
            preview_h=preview_h,
            fps=job_info.fps,
            loop_seconds=loop_seconds,
        ),
        diag,
    )


@router.websocket("/preview/clip")
async def preview_clip_ws(websocket: WebSocket) -> None:
    await _preview_clip_ws_impl(websocket)


async def _preview_clip_ws_impl(websocket: WebSocket) -> None:
    await websocket.accept()
    log.info("clip preview WebSocket connected")

    session: _ClipSession | None = None
    last_fingerprint: str | None = None
    error_frame_cache: dict[tuple[int, int], bytes] = {}

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            prepare_warnings_to_send = None

            job_w = max(1, int(msg.get("width") or 1920))
            job_h = max(1, int(msg.get("height") or 1080))
            preview_w, preview_h = preview_dimensions(
                job_w,
                job_h,
                max_long_side=MAX_PREVIEW_LONG_SIDE,
            )
            loop_seconds = _clamp_loop_seconds(msg.get("loop_seconds"))
            t = max(0.0, float(msg.get("t") or 0.0))
            if t > loop_seconds:
                t = t % loop_seconds

            clip_payload = msg.get("clip")
            if not isinstance(clip_payload, dict):
                await _send_preview_bytes(websocket, b"")
                continue

            if clip_payload.get("enabled") is False:
                if session is not None:
                    await release_compositor(session.compositor)
                session = None
                last_fingerprint = None
                await _send_preview_bytes(websocket, b"")
                continue

            fp = _fingerprint(msg, preview_w, preview_h)
            if fp != last_fingerprint:
                ensure_plugins_registered()
                try:
                    if session is not None:
                        await release_compositor(session.compositor)
                    session, diag = await _prepare_session(msg, preview_w, preview_h, loop_seconds)
                    last_fingerprint = fp
                    prepare_warnings_to_send = diag
                except Exception as exc:
                    log.warning(
                        "clip preview prepare failed — %s (%s)",
                        clip_payload.get("clip_type") if isinstance(clip_payload, dict) else "?",
                        exc,
                        exc_info=True,
                    )
                    if session is not None:
                        await release_compositor(session.compositor)
                    session = None
                    last_fingerprint = None
                    await _send_preview_text(
                        websocket, json.dumps({"error": f"prepare failed: {exc}"})
                    )
                    continue

            if session is None:
                await _send_preview_bytes(websocket, b"")
                continue

            try:
                frame_bytes = await render_preview_frame(session.compositor, t, session.fps)
                header = struct.pack("<II", session.preview_w, session.preview_h)
                await _send_preview_bytes(websocket, header + frame_bytes)
                if prepare_warnings_to_send is not None:
                    await _send_preview_text(
                        websocket, json.dumps(prepare_warnings_event(prepare_warnings_to_send))
                    )
            except WebSocketDisconnect:
                raise
            except Exception as exc:
                clip_type = clip_payload.get("clip_type") if isinstance(clip_payload, dict) else "?"
                log.warning(
                    "clip preview draw failed — %s at t=%.3f: %s",
                    clip_type,
                    t,
                    exc,
                    exc_info=True,
                )
                key = (session.preview_w, session.preview_h)
                if key not in error_frame_cache:
                    error_frame_cache[key] = await asyncio.get_event_loop().run_in_executor(
                        None, render_error_frame, key[0], key[1]
                    )
                header = struct.pack("<II", session.preview_w, session.preview_h)
                try:
                    await _send_preview_bytes(websocket, header + error_frame_cache[key])
                    await _send_preview_text(
                        websocket,
                        json.dumps(
                            {
                                "event": "draw_error",
                                "message": str(exc),
                                "clip_type": clip_type,
                            }
                        ),
                    )
                except WebSocketDisconnect:
                    raise

    except WebSocketDisconnect:
        log.info("clip preview WebSocket disconnected")
    except Exception as exc:
        log.error("clip preview WebSocket error — %s", exc, exc_info=True)
    finally:
        if session is not None:
            await release_compositor(session.compositor)
