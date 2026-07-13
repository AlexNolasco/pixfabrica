"""Preview WebSocket endpoint.

WS /preview

Receives JSON messages from the client:
  { "graph": <Graph JSON>, "t": <float seconds>, "fps": <float> }  — full (first / after edit)
  { "t": <float seconds>, "fps": <float> }                         — lightweight scrub/play

Renders a single frame at time `t` at preview resolution and sends back raw RGBA
bytes. The client blits them onto a <canvas> with putImageData().

A persistent session is kept per connection so that `prepare()` is only called
once per unique graph (keyed by graph hash). Scrubbing only calls composite().
"""

from __future__ import annotations

import hashlib
import json
import logging
import struct
from contextlib import suppress
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from uvicorn.protocols.utils import ClientDisconnected

from pixfabrica_api.gl_policy import gl_graph_violation
from pixfabrica_api.license_policy import license_graph_violation
from pixfabrica_api.plugin_registry import ensure_plugins_registered
from pixfabrica_api.preview_runtime import (
    PrepareOptions,
    prepare_compositor,
    release_compositor,
    release_compositor_gl,
    render_preview_frame,
    skia_surface_rgba_bytes,
)
from pixfabrica_api.project_limits import graph_policy_violation
from pixfabrica_api.server_config import MAX_PREVIEW_LONG_SIDE
from pixfabrica_core.audio.timeline_store import TimelineMemoryStore
from pixfabrica_core.clips import RenderJob
from pixfabrica_core.composition.unknown import UnknownClip
from pixfabrica_core.prepare_diagnostics import prepare_warnings_event
from pixfabrica_core.preview_dims import preview_dimensions
from pixfabrica_core.preview_invalidation import (
    ReprepareScope,
    job_uses_gl_tracks,
    preview_audio_prepare_hash,
    resolve_reprepare_scope,
)
from pixfabrica_renderer.compositor import Compositor

log = logging.getLogger("pixfabrica.api.preview")

router = APIRouter(tags=["preview"])


def _graph_hash(graph_data: dict[str, Any]) -> str:
    return hashlib.md5(json.dumps(graph_data, sort_keys=True).encode()).hexdigest()


def _unknown_clip_types(job: RenderJob) -> list[str]:
    unknown: list[str] = []
    for track in job.tracks:
        for clip in track.clips:
            if isinstance(clip, UnknownClip):
                unknown.append(clip.raw_clip_type or "<missing clip_type>")
    return unknown


# Backwards-compatible aliases for tests / clip preview route.
_skia_surface_rgba_bytes = skia_surface_rgba_bytes


def _render_frame(compositor: Compositor, t: float, fps: float) -> bytes:
    from pixfabrica_api.preview_runtime import render_frame

    return render_frame(compositor, t, fps)


@router.websocket("/preview")
async def preview_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    log.info("preview WebSocket connected")

    compositor: Compositor | None = None
    last_graph_hash: str | None = None
    last_audio_hash: str | None = None
    preview_w = preview_h = 0
    timeline_store = TimelineMemoryStore()

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            prepare_warnings_to_send = None

            t: float = float(msg.get("t", 0.0))
            graph_data: dict[str, Any] | None = msg.get("graph")
            full_res: bool = bool(msg.get("fullRes", False))

            if full_res:
                if not graph_data:
                    await websocket.send_text(json.dumps({"error": "graph_required"}))
                    continue
                ensure_plugins_registered()
                limit_err = graph_policy_violation(graph_data)
                if limit_err:
                    await websocket.send_text(json.dumps({"error": limit_err}))
                    continue
                gl_err = gl_graph_violation(graph_data)
                if gl_err:
                    await websocket.send_text(json.dumps({"error": gl_err}))
                    continue
                license_err = license_graph_violation(graph_data)
                if license_err:
                    await websocket.send_text(json.dumps({"error": license_err}))
                    continue
                try:
                    job = RenderJob.model_validate(graph_data)
                except Exception as exc:
                    await websocket.send_text(json.dumps({"error": str(exc)}))
                    continue
                unknown_types = _unknown_clip_types(job)
                if unknown_types:
                    err = f"unknown clip type(s): {', '.join(sorted(set(unknown_types)))}"
                    await websocket.send_text(json.dumps({"error": err}))
                    continue
                snap_w, snap_h = int(job.width), int(job.height)
                snap_compositor: Compositor | None = None
                try:
                    snap_compositor, _snap_diag = await prepare_compositor(
                        job,
                        snap_w,
                        snap_h,
                        scale_typography_to_preview=False,
                        timeline_store=timeline_store,
                    )
                    fps = float(msg.get("fps", 20.0))
                    frame_bytes = await render_preview_frame(snap_compositor, t, fps)
                    header = struct.pack("<II", snap_w, snap_h)
                    await websocket.send_bytes(header + frame_bytes)
                except (WebSocketDisconnect, ClientDisconnected):
                    raise
                except Exception as exc:
                    log.error("preview: fullRes render error at t=%.3f — %s", t, exc, exc_info=True)
                    with suppress(WebSocketDisconnect, ClientDisconnected, RuntimeError):
                        await websocket.send_text(json.dumps({"error": str(exc)}))
                finally:
                    await release_compositor(snap_compositor)
                    # Full-res prepare/render runs on the shared preview GL thread; the
                    # live session compositor must be rebuilt before the next preview frame.
                    await release_compositor(compositor)
                    compositor = None
                    last_graph_hash = None
                    last_audio_hash = None
                continue

            if not graph_data:
                if compositor is None:
                    await websocket.send_text(json.dumps({"error": "graph_required"}))
                    continue
            else:
                gh = _graph_hash(graph_data)
                graph_changed = gh != last_graph_hash
                force_reprepare = bool(msg.get("reprepare", False))

                if graph_changed or force_reprepare:
                    ensure_plugins_registered()
                    limit_err = graph_policy_violation(graph_data)
                    if limit_err:
                        log.warning("preview: policy limit — %s", limit_err.get("detail"))
                        await websocket.send_text(json.dumps({"error": limit_err}))
                        await release_compositor(compositor)
                        compositor = None
                        last_graph_hash = None
                        last_audio_hash = None
                        continue
                    gl_err = gl_graph_violation(graph_data)
                    if gl_err:
                        log.warning("preview: gl unavailable — %s", gl_err.get("detail"))
                        await websocket.send_text(json.dumps({"error": gl_err}))
                        await release_compositor(compositor)
                        compositor = None
                        last_graph_hash = None
                        last_audio_hash = None
                        continue
                    license_err = license_graph_violation(graph_data)
                    if license_err:
                        log.warning("preview: license policy — %s", license_err.get("detail"))
                        await websocket.send_text(json.dumps({"error": license_err}))
                        await release_compositor(compositor)
                        compositor = None
                        last_graph_hash = None
                        last_audio_hash = None
                        continue
                    try:
                        job = RenderJob.model_validate(graph_data)
                    except Exception as exc:
                        log.warning("preview: invalid graph — %s", exc)
                        await websocket.send_text(json.dumps({"error": str(exc)}))
                        continue

                    unknown_types = _unknown_clip_types(job)
                    if unknown_types:
                        err = f"unknown clip type(s): {', '.join(sorted(set(unknown_types)))}"
                        log.warning("preview: %s", err)
                        await websocket.send_text(json.dumps({"error": err}))
                        await release_compositor(compositor)
                        compositor = None
                        last_graph_hash = None
                        last_audio_hash = None
                        continue

                    preview_w, preview_h = preview_dimensions(
                        job.width,
                        job.height,
                        max_long_side=MAX_PREVIEW_LONG_SIDE,
                    )

                    audio_h = preview_audio_prepare_hash(graph_data)
                    audio_changed = last_audio_hash is None or audio_h != last_audio_hash
                    scope = resolve_reprepare_scope(
                        graph_changed=graph_changed,
                        force_reprepare=force_reprepare,
                        audio_hash_changed=audio_changed,
                        uses_gl=job_uses_gl_tracks(job),
                    )

                    reuse_audio = None
                    old_tracks = None
                    if compositor is not None:
                        if scope in (ReprepareScope.SKIP_AUDIO, ReprepareScope.GL_CONTEXT_ONLY):
                            reuse_audio = compositor._audio
                        if scope == ReprepareScope.GL_CONTEXT_ONLY:
                            old_tracks = compositor._tracks

                    try:
                        if scope == ReprepareScope.GL_CONTEXT_ONLY:
                            await release_compositor_gl(compositor)
                        else:
                            await release_compositor(compositor)
                        log.info(
                            "preview: reprepare scope=%s audio_changed=%s graph_changed=%s",
                            scope.value,
                            audio_changed,
                            graph_changed,
                        )
                        compositor, diag = await prepare_compositor(
                            job,
                            preview_w,
                            preview_h,
                            scale_typography_to_preview=True,
                            timeline_store=timeline_store,
                            prepare_options=PrepareOptions(
                                scope=scope,
                                reuse_audio_timeline=reuse_audio,
                                old_tracks=old_tracks,
                            ),
                        )
                        last_graph_hash = gh
                        last_audio_hash = audio_h
                        prepare_warnings_to_send = diag
                    except Exception as exc:
                        log.error("preview: prepare failed — %s", exc, exc_info=True)
                        await websocket.send_text(json.dumps({"error": f"prepare failed: {exc}"}))
                        compositor = None
                        last_graph_hash = None
                        last_audio_hash = None
                        continue

            if compositor is None:
                await websocket.send_text(json.dumps({"error": "graph_required"}))
                continue

            try:
                fps = float(msg.get("fps", 20.0))
                frame_bytes = await render_preview_frame(compositor, t, fps)
                header = struct.pack("<II", preview_w, preview_h)
                await websocket.send_bytes(header + frame_bytes)
                if prepare_warnings_to_send is not None:
                    await websocket.send_text(
                        json.dumps(prepare_warnings_event(prepare_warnings_to_send))
                    )
            except (WebSocketDisconnect, ClientDisconnected):
                raise
            except Exception as exc:
                log.error("preview: render error at t=%.3f — %s", t, exc, exc_info=True)
                with suppress(WebSocketDisconnect, ClientDisconnected, RuntimeError):
                    await websocket.send_text(json.dumps({"error": str(exc)}))

    except WebSocketDisconnect:
        log.info("preview WebSocket disconnected")
    except Exception as exc:
        log.error("preview WebSocket error — %s", exc, exc_info=True)
    finally:
        await release_compositor(compositor)
