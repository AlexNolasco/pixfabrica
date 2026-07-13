"""Preview analyzes sounds wired to visuals or bus-active per-clip effects."""

from __future__ import annotations

from typing import ClassVar

from pixfabrica_core.audio.mixin import AudioVisualMixin
from pixfabrica_core.audio.preview_prepare import (
    bus_names_needed_for_clip,
    preview_bus_names_needed_by_visuals,
    sounds_for_preview_prepare,
)
from pixfabrica_core.audio.sound import SoundClip
from pixfabrica_core.clips import ClipSkia, RenderJob
from pixfabrica_core.composition.track import SkiaTrack
from pixfabrica_std_effects.effects.blur_skia import BlurSkia


class _BusStub(AudioVisualMixin, ClipSkia):
    clip_type: ClassVar[str] = "test-bus-stub"

    async def prepare(self, ctx, bounds=None) -> None:
        pass

    def draw(self, ctx) -> None:
        pass


class _PlainStub(ClipSkia):
    clip_type: ClassVar[str] = "test-plain-stub"

    async def prepare(self, ctx, bounds=None) -> None:
        pass

    def draw(self, ctx) -> None:
        pass


def _job(
    *,
    sound_bus: str = "drums",
    bus_select: str | None = None,
    sound_enabled: bool = True,
) -> RenderJob:
    clip = _BusStub(
        id="el1",
        start=0.0,
        duration=10.0,
        bus_select=bus_select,
    )
    track = SkiaTrack(id="t1", start=0.0, duration=10.0, clips=[clip])
    sound = SoundClip(
        id="s1",
        bus=sound_bus,
        source="/fake/audio.mp3",
        enabled=sound_enabled,
    )
    return RenderJob(
        title="t",
        description="d",
        duration=10.0,
        tracks=[track],
        sounds=[sound],
    )


def test_no_explicit_bus_select_skips_sound_prepare() -> None:
    job = _job(bus_select=None)
    assert preview_bus_names_needed_by_visuals(job) == set()
    assert sounds_for_preview_prepare(job) == []


def test_empty_bus_select_skips_sound_prepare() -> None:
    job = _job(bus_select="  ")
    assert sounds_for_preview_prepare(job) == []


def test_matching_bus_select_includes_sound() -> None:
    job = _job(bus_select="drums", sound_bus="drums")
    assert preview_bus_names_needed_by_visuals(job) == {"drums"}
    assert sounds_for_preview_prepare(job) == [job.sounds[0]]


def test_mismatched_bus_select_skips_sound() -> None:
    job = _job(bus_select="main", sound_bus="drums")
    assert preview_bus_names_needed_by_visuals(job) == {"main"}
    assert sounds_for_preview_prepare(job) == []


def test_disabled_sound_excluded_even_when_bus_matches() -> None:
    job = _job(bus_select="drums", sound_bus="drums", sound_enabled=False)
    assert sounds_for_preview_prepare(job) == []


def test_bus_active_effect_on_plain_clip_includes_sound() -> None:
    clip = _PlainStub(
        id="img1",
        start=0.0,
        duration=10.0,
        effects=[
            BlurSkia(
                id="fx1",
                bus_select="drums",
                sensitivity=0.5,
            )
        ],
    )
    track = SkiaTrack(id="t1", start=0.0, duration=10.0, clips=[clip])
    sound = SoundClip(id="s1", bus="drums", source="/fake/audio.mp3")
    job = RenderJob(title="t", description="d", duration=10.0, tracks=[track], sounds=[sound])
    assert preview_bus_names_needed_by_visuals(job) == {"drums"}
    assert sounds_for_preview_prepare(job) == [sound]


def test_bus_active_effect_without_bus_select_defaults_to_main() -> None:
    clip = _PlainStub(
        id="img1",
        start=0.0,
        duration=10.0,
        effects=[BlurSkia(id="fx1", sensitivity=0.5)],
    )
    track = SkiaTrack(id="t1", start=0.0, duration=10.0, clips=[clip])
    sound = SoundClip(id="s1", bus="main", source="/fake/audio.mp3")
    job = RenderJob(title="t", description="d", duration=10.0, tracks=[track], sounds=[sound])
    assert preview_bus_names_needed_by_visuals(job) == {"main"}
    assert sounds_for_preview_prepare(job) == [sound]


def test_static_effect_bus_select_does_not_require_sound_prepare() -> None:
    clip = _PlainStub(
        id="img1",
        start=0.0,
        duration=10.0,
        effects=[BlurSkia(id="fx1", bus_select="drums", sensitivity=0.0)],
    )
    track = SkiaTrack(id="t1", start=0.0, duration=10.0, clips=[clip])
    sound = SoundClip(id="s1", bus="drums", source="/fake/audio.mp3")
    job = RenderJob(title="t", description="d", duration=10.0, tracks=[track], sounds=[sound])
    assert preview_bus_names_needed_by_visuals(job) == set()
    assert sounds_for_preview_prepare(job) == []


def test_bus_names_needed_for_clip_plain_blur() -> None:
    clip = _PlainStub(
        id="img1",
        start=0.0,
        duration=10.0,
        effects=[BlurSkia(id="fx1", bus_select="drums", sensitivity=0.5)],
    )
    assert bus_names_needed_for_clip(clip) == {"drums"}


def test_bus_names_needed_for_clip_multi_bus() -> None:
    clip = _BusStub(
        id="el1",
        start=0.0,
        duration=10.0,
        bus_select="main",
        effects=[BlurSkia(id="fx1", bus_select="drums", sensitivity=0.5)],
    )
    assert bus_names_needed_for_clip(clip) == {"drums", "main"}


def test_bus_names_needed_for_clip_static_blur_excluded() -> None:
    clip = _PlainStub(
        id="img1",
        start=0.0,
        duration=10.0,
        effects=[BlurSkia(id="fx1", bus_select="drums", sensitivity=0.0)],
    )
    assert bus_names_needed_for_clip(clip) == set()
