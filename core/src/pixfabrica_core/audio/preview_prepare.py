"""Which sounds composition preview should analyze before compositing."""

from __future__ import annotations

from pixfabrica_core.audio.bus import effective_bus_name
from pixfabrica_core.audio.mixin import AudioVisualMixin
from pixfabrica_core.audio.sound import SoundClip
from pixfabrica_core.clips.visual import VisualClip
from pixfabrica_core.composition.effect_def import (
    effect_bus_active,
    effect_supports_bus,
    resolve_effect_bus_select,
)
from pixfabrica_core.composition.job import RenderJob


def bus_names_needed_for_clip(clip: VisualClip) -> set[str]:
    """Bus names referenced by an enabled visual clip and its bus-active effects."""
    needed: set[str] = set()
    if not clip.enabled:
        return needed
    if isinstance(clip, AudioVisualMixin):
        raw = (clip.bus_select or "").strip()
        if raw:
            needed.add(effective_bus_name(clip.bus_select))
    for fx in clip.effects:
        if not fx.enabled:
            continue
        if not effect_supports_bus(fx) or not effect_bus_active(fx):
            continue
        needed.add(
            effective_bus_name(resolve_effect_bus_select(fx, clip)),
        )
    return needed


def preview_bus_names_needed_by_visuals(job: RenderJob) -> set[str]:
    """Bus names referenced by enabled visuals and bus-active per-clip effects."""
    needed: set[str] = set()
    for track in job.tracks:
        if not track.enabled:
            continue
        for clip in track.clips:
            if not isinstance(clip, VisualClip):
                continue
            needed |= bus_names_needed_for_clip(clip)
    return needed


def sounds_for_preview_prepare(job: RenderJob) -> list[SoundClip]:
    """Enabled sounds whose bus is referenced by a visual clip or bus-active effect."""
    needed = preview_bus_names_needed_by_visuals(job)
    if not needed:
        return []
    out: list[SoundClip] = []
    for sound in job.sounds:
        if not isinstance(sound, SoundClip) or not sound.enabled:
            continue
        bus = sound.bus.strip()
        if bus and bus in needed:
            out.append(sound)
    return out
