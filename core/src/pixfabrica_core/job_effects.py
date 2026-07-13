"""Job-level helpers for per-clip effects (parallelism, singleton scan)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pixfabrica_core.clips import RenderJob, VisualClip
from pixfabrica_core.composition.effect_def import (
    EffectBackend,
    clip_has_enabled_effects,
    enabled_effects,
    track_has_enabled_effects,
)
from pixfabrica_core.composition.effect_registry import get_effect_class
from pixfabrica_core.composition.unknown import UnknownEffect

if TYPE_CHECKING:
    from pixfabrica_core.composition.track import TrackClip


def iter_visual_clips(job: RenderJob):
    for track in job.tracks:
        for clip in track.clips:
            if isinstance(clip, VisualClip):
                yield clip


def job_has_enabled_effects(job: RenderJob) -> bool:
    for track in job.tracks:
        if track_has_enabled_effects(track.effects):
            return True
    return any(clip_has_enabled_effects(clip.effects) for clip in iter_visual_clips(job))


def job_requires_single_process(job: RenderJob) -> bool:
    """True when any enabled effect plugin declares ``singleton: true``."""
    for track in job.tracks:
        for fx in enabled_effects(track.effects):
            if isinstance(fx, UnknownEffect):
                continue
            if type(fx).singleton:
                return True
    for clip in iter_visual_clips(job):
        for fx in enabled_effects(clip.effects):
            if isinstance(fx, UnknownEffect):
                continue
            if type(fx).singleton:
                return True
    return False


def resolve_parallelism(job: RenderJob) -> str:
    """Return effective parallelism after singleton downgrade."""
    if job_requires_single_process(job):
        return "single"
    return job.parallelism


def chain_backend_for_clip(clip: VisualClip) -> EffectBackend | None:
    active = enabled_effects(clip.effects)
    if not active:
        return None
    return type(active[0]).effect_backend


def chain_backend_for_track(track: TrackClip) -> EffectBackend | None:
    active = enabled_effects(track.effects)
    if not active:
        return None
    return type(active[0]).effect_backend


def chain_backend_for_effect_type(effect_type: str) -> EffectBackend | None:
    cls = get_effect_class(effect_type)
    if cls is None:
        return None
    return cls.effect_backend


def clip_needs_gl_effect_pipeline(clip: VisualClip, *, for_preview: bool) -> bool:
    """True when a clip runs a GL per-clip effect chain this frame."""
    if chain_backend_for_clip(clip) != "gl":
        return False
    if not clip_has_enabled_effects(clip.effects):
        return False
    if not for_preview:
        return True
    return any(not type(fx).skip_in_preview for fx in enabled_effects(clip.effects))


def track_needs_gl_effect_pipeline(track: TrackClip, *, for_preview: bool) -> bool:
    """True when a track runs a GL effect chain on its composite this frame."""
    if chain_backend_for_track(track) != "gl":
        return False
    if not track_has_enabled_effects(track.effects):
        return False
    if not for_preview:
        return True
    return any(not type(fx).skip_in_preview for fx in enabled_effects(track.effects))


def tracks_need_gl_context(tracks: list[TrackClip], *, for_preview: bool = False) -> bool:
    """True when compositor must own a ModernGL context (GL tracks or GL effect chains)."""
    from pixfabrica_core.composition.track import GLEffectTrack, GLTrack

    for track in tracks:
        if isinstance(track, (GLTrack, GLEffectTrack)):
            return True
        if track_needs_gl_effect_pipeline(track, for_preview=for_preview):
            return True
        for clip in track.clips:
            if isinstance(clip, VisualClip) and clip_needs_gl_effect_pipeline(
                clip, for_preview=for_preview
            ):
                return True
    return False
