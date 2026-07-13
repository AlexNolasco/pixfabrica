from __future__ import annotations

import logging
from typing import Any, ClassVar, Protocol, runtime_checkable

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from pixfabrica_core.audio.bus import AudioBusFrame
from pixfabrica_core.clips.base import (
    Clip,
    JobInfo,
    PrepareContext,
    TimeState,
)
from pixfabrica_core.composition.effect_def import EffectInstance, validate_effect_chain
from pixfabrica_core.graphics import Rect


# ==========================================
# 1. THE PROTOCOLS (Interfaces)
# ==========================================
@runtime_checkable
class ClipTypeProtocol(Protocol):
    """
    Contract the plugin loader uses to discover and validate plugin-contributed clip types.
    Any Clip subclass with a clip_type ClassVar satisfies this automatically.
    """

    clip_type: ClassVar[str]

    def model_dump(self) -> dict[str, Any]: ...

    @classmethod
    def model_json_schema(cls) -> dict[str, Any]: ...


@runtime_checkable
class DrawableProtocol(ClipTypeProtocol, Protocol):
    """Visual contract: clip types that draw must implement this."""

    def draw(self, ctx: RenderContext) -> None: ...


# ==========================================
# 2. THE BASE CLASSES (Abstract Implementations)
# ==========================================
class RenderContext(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    job: JobInfo
    time: TimeState
    bounds: Rect  # region this clip renders into
    canvas: Any
    source_texture: Any = None  # moderngl.Texture snapshot; populated for GLPostProcessClip
    # Per-call audio frame for this clip (only populated for AudioVisualMixin clips
    # whose bus_select resolved). Defaults to a zero frame so plugins can read it
    # unconditionally inside draw().
    audio_bus_frame: AudioBusFrame = Field(default_factory=AudioBusFrame.zero)
    # Fraction of ``bounds`` width/height padded on each side in the parent canvas.
    overscan: float = 0.0
    log: logging.Logger = Field(default_factory=lambda: logging.getLogger("pixfabrica.render"))


class VisualClip(Clip):
    """Abstract base for all renderable clip types. Subclass ClipSkia or ClipGL, not this directly.

    Plugin contract — STATELESS draw():
        ``draw(ctx)`` MUST be a pure function of ``self`` (post-prepare),
        ``ctx.time.frame``, ``ctx.bounds``, ``ctx.canvas``, and
        ``ctx.audio_bus_frame``. It MUST NOT mutate any cross-frame state
        (e.g. EMAs, deques, scroll positions, "last frame" markers, BPM
        accumulators) on ``self``. Calling ``draw(F)`` for any frame ``F``
        in any order MUST produce identical pixel output.

        Why: the parallel renderer (``RenderJob.parallelism = "multi"``)
        ships frames to N worker processes out of order; per-frame
        accumulator state on ``self`` is therefore corrupted and visibly
        broken. The serial renderer happens to give the "expected"
        sequential semantics, but stateful ``draw()`` is a latent bug
        either way.

        How: any temporal smoothing, beat history, scroll trajectory, etc.
        must be precomputed for the whole job in ``prepare()`` (which has
        access to the resolved ``ctx.audio: AudioTimeline`` and
        ``ctx.job.total_frames``) and stored as an immutable per-frame
        lookup table (typically a ``numpy.ndarray``) that ``draw()`` only
        reads. See ``std-spectrum-bars`` and ``std-audio-debug`` for
        reference implementations.

        ``PrivateAttr`` slots populated once in ``prepare()`` (compiled
        shaders, baked images, parsed segments, layout caches, decoder
        handles, per-frame lookup tables) are fine — those are setup
        artefacts, not per-frame state.
    """

    backend: ClassVar[str] = ""
    effects: list[EffectInstance] = Field(default_factory=list)

    @field_validator("effects", mode="before")
    @classmethod
    def _coerce_effects(cls, value: Any) -> list[EffectInstance]:
        from pixfabrica_core.composition.effect_registry import deserialize_effects

        if value is None:
            return []
        if not isinstance(value, list):
            return []
        if value and all(isinstance(item, EffectInstance) for item in value):
            return list(value)
        return deserialize_effects(value)

    @model_validator(mode="after")
    def _validate_effects(self) -> VisualClip:
        validate_effect_chain(self.effects)
        return self

    async def prepare(self, _ctx: PrepareContext, _bounds: Rect | None = None) -> None:
        raise NotImplementedError(f"{self.__class__.__name__} must implement prepare()")

    def draw(self, _ctx: RenderContext) -> None:
        raise NotImplementedError(f"{self.__class__.__name__} must implement draw()")


class ClipSkia(VisualClip):
    """Base for 2D clip types rendered with Skia. ctx.canvas is a skia.Canvas at runtime."""

    backend: ClassVar[str] = "skia"


class ClipGL(VisualClip):
    """Base for GPU clip types rendered with ModernGL. ctx.canvas is a moderngl.Framebuffer at runtime."""

    backend: ClassVar[str] = "gl"


class GLPostProcessClip(ClipGL):
    """Base for GL clips that post-process the entire composited frame.

    Place on a :class:`~pixfabrica_core.composition.track.GLEffectTrack` (``std-post-track``)
    — at most one such clip per effect row. The compositor snapshots the current
    Skia canvas (all previous tracks) and passes it as ``ctx.source_texture`` (a
    ``moderngl.Texture``) before calling ``draw()``.
    """

    backend: ClassVar[str] = "gl"
