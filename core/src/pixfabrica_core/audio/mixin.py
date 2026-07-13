from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from pixfabrica_core.audio.bus import (
    AudioBusFrame,
    AudioTimeline,
    bus_timeline_for_select,
    resolve_audio_bus_frame_for_clip,
)

if TYPE_CHECKING:
    from pixfabrica_core.clips.base import PrepareContext
    from pixfabrica_core.clips.visual import RenderContext


class AudioVisualMixin(BaseModel):
    """Mixin for VisualClips that react to an audio bus.

    Declare before the backend base class in the MRO:
        class RainClip(AudioVisualMixin, ClipGL): ...

    Read the current frame's audio inside ``draw()`` via ``self.audio(ctx)``.
    """

    bus_select: str | None = None
    sensitivity: float = Field(
        default=1.0,
        ge=0.1,
        le=8.0,
        multiple_of=0.05,
        description="Audio response gain (1 = default job-wide normalization)",
    )

    def scale_audio(self, value: float) -> float:
        """Clamp ``value * sensitivity`` to 0..1 — use for bus scalars and spectrum bins."""
        return min(1.0, max(0.0, float(value) * float(self.sensitivity)))

    def audio(self, ctx: RenderContext) -> AudioBusFrame:
        return ctx.audio_bus_frame

    def bus_timeline(self, ctx: PrepareContext) -> list[AudioBusFrame] | None:
        """Resolved flat bus frames for prepare()-time precomputation."""
        return bus_timeline_for_select(ctx.audio, self.bus_select)

    def bus_active_for_draw(self, ctx: RenderContext) -> bool:
        if (self.bus_select or "").strip():
            return True
        af = ctx.audio_bus_frame
        return af.amplitude > 0 or af.bass > 0 or af.mid > 0 or af.high > 0

    def resolve_bus_frame(
        self,
        *,
        audio: AudioTimeline,
        frame: int,
    ) -> AudioBusFrame:
        return resolve_audio_bus_frame_for_clip(
            audio=audio,
            bus_select=self.bus_select,
            frame=frame,
        )
