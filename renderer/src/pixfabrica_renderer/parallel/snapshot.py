"""JSON-safe handoff of resolved render inputs, never GPU resources or project files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from pixfabrica_core.audio.bus import AudioTimeline
from pixfabrica_core.clips import JobInfo, RenderJob, VisualClip
from pixfabrica_core.composition.effect_registry import register_effect
from pixfabrica_core.composition.registry import register_clip_type, register_setting_type
from pixfabrica_core.composition.unknown import UnknownClip, UnknownEffect, UnknownProjectSetting
from pixfabrica_core.errors import RenderError, RenderErrorCode
from pixfabrica_core.plugins.discovery import discover_plugins
from pixfabrica_core.prepare_diagnostics import PrepareWarning


class _Snapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["resolved-render-v1"]
    job: dict[str, Any]
    info: JobInfo
    audio: AudioTimeline
    variable_warnings: list[PrepareWarning]


@dataclass(frozen=True)
class ResolvedRender:
    job: RenderJob
    info: JobInfo
    audio: AudioTimeline


def encode_render_snapshot(job: RenderJob, info: JobInfo, audio: AudioTimeline) -> str:
    """Capture a validated job after parent preparation, using effective render settings.

    Concrete models preserve subclass fields and ClassVar wire identifiers.
    JSON detaches the snapshot from subsequent mutations and excludes private caches.
    """
    validate_render_plugins(job)
    payload = job.model_dump(mode="json")
    payload["tracks"] = [_dump_track(track) for track in job.tracks]
    payload["sounds"] = [_dump_sound(sound) for sound in job.sounds]
    if job.theme is not None:
        payload["theme"] = _dump_project_setting(job.theme)
    if job.typography_setting is not None:
        payload["typography_setting"] = _dump_project_setting(job.typography_setting)
    return _Snapshot(
        kind="resolved-render-v1",
        job=payload,
        info=info,
        audio=audio,
        variable_warnings=job.project_variable_warnings(),
    ).model_dump_json()


def restore_render_snapshot(payload: str, *, plugins_dir: str | None = None) -> ResolvedRender:
    """Restore a parent snapshot in a fresh process, without repeating resolution.

    Register plugins before decoding composition types and fail on missing plugins.
    Visual prepare and all GPU allocations remain the worker's responsibility.
    """
    snapshot = _Snapshot.model_validate_json(payload)
    discovered, _failed = discover_plugins(Path(plugins_dir) if plugins_dir else None)
    for plugin in discovered:
        for clip_cls in plugin.clip_types:
            register_clip_type(clip_cls)
        for setting_cls in plugin.project_settings:
            register_setting_type(setting_cls)
        for effect_cls in plugin.effects:
            register_effect(effect_cls)
    job = RenderJob.restore_resolved(snapshot.job, warnings=snapshot.variable_warnings)
    validate_render_plugins(job)
    return ResolvedRender(job, snapshot.info, snapshot.audio)


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


def validate_render_plugins(job: RenderJob) -> None:
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
