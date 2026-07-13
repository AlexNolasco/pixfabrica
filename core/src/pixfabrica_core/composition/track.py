from __future__ import annotations

import asyncio
from dataclasses import replace
from enum import StrEnum
from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, Field, PrivateAttr, field_validator, model_validator

from pixfabrica_core.clips.base import Clip, ClipCategory, PrepareContext
from pixfabrica_core.composition.effect_def import EffectInstance, validate_effect_chain
from pixfabrica_core.composition.effect_registry import deserialize_effects
from pixfabrica_core.easing import EasingType
from pixfabrica_core.graphics import Rect

HEADER_FRACTION_MIN = 0.1
HEADER_FRACTION_MAX = 0.5
DEFAULT_HEADER_FRACTION = 0.2


def _compute_banded_layout(
    track: Rect,
    n: int,
    header_fraction: float | None,
    *,
    vertical: bool,
) -> list[Rect]:
    if n == 0:
        return []
    if n != 2 or header_fraction is None:
        if vertical:
            band = track.height / n
            return [Rect(track.x, track.y + i * band, track.width, band) for i in range(n)]
        band = track.width / n
        return [Rect(track.x + i * band, track.y, band, track.height) for i in range(n)]

    if vertical:
        first_size = track.height * header_fraction
        second_size = track.height - first_size
        return [
            Rect(track.x, track.y, track.width, first_size),
            Rect(track.x, track.y + first_size, track.width, second_size),
        ]

    first_size = track.width * header_fraction
    second_size = track.width - first_size
    return [
        Rect(track.x, track.y, first_size, track.height),
        Rect(track.x + first_size, track.y, second_size, track.height),
    ]


class FillLayout(BaseModel):
    """Each clip receives the full track area."""

    type: Literal["fill"] = "fill"

    def compute(self, track: Rect, n: int) -> list[Rect]:
        return [track] * n


class VerticalLayout(BaseModel):
    """Splits the track into horizontal bands (top to bottom).

    With exactly two clips and ``header_fraction`` set, clip 0 receives the
    leading band and clip 1 receives the remainder. Otherwise bands are equal.
    """

    type: Literal["vertical"] = "vertical"
    header_fraction: float | None = Field(
        default=None,
        ge=HEADER_FRACTION_MIN,
        le=HEADER_FRACTION_MAX,
        description="First band size as a fraction of track height (two clips only).",
    )

    def compute(self, track: Rect, n: int) -> list[Rect]:
        return _compute_banded_layout(track, n, self.header_fraction, vertical=True)


class HorizontalLayout(BaseModel):
    """Splits the track into vertical bands (left to right).

    With exactly two clips and ``header_fraction`` set, clip 0 receives the
    leading band and clip 1 receives the remainder. Otherwise bands are equal.
    """

    type: Literal["horizontal"] = "horizontal"
    header_fraction: float | None = Field(
        default=None,
        ge=HEADER_FRACTION_MIN,
        le=HEADER_FRACTION_MAX,
        description="First band size as a fraction of track width (two clips only).",
    )

    def compute(self, track: Rect, n: int) -> list[Rect]:
        return _compute_banded_layout(track, n, self.header_fraction, vertical=False)


LayoutType = Annotated[
    FillLayout | VerticalLayout | HorizontalLayout,
    Field(discriminator="type"),
]


# ── Transitions ──────────────────────────────────────────────────────────────


class TransitionType(StrEnum):
    FADE = "fade"
    SLIDE = "slide"
    SCALE = "scale"
    BLUR = "blur"
    WIPE = "wipe"


class TrackTransition(BaseModel):
    """Defines a track intro or outro transition."""

    type: TransitionType = TransitionType.FADE
    duration: float = Field(default=0.5, gt=0.0, le=30.0)
    easing: EasingType = EasingType.EASE_IN_OUT
    direction: Literal["left", "right", "up", "down"] = "left"


# ── Tracks ───────────────────────────────────────────────────────────────────


class TrackClip(Clip):
    """Base track — owns a canvas and composites children in array order (first = bottom, last = top)."""

    clip_type: ClassVar[str] = ""
    clip_category: ClassVar[ClipCategory] = ClipCategory.TRACK
    backend: ClassVar[str] = ""  # set by SkiaTrack / GLTrack
    layout: LayoutType = Field(default_factory=FillLayout)
    clips: list[Clip] = Field(default_factory=list)
    effects: list[EffectInstance] = Field(default_factory=list)
    transition_in: TrackTransition | None = None
    transition_out: TrackTransition | None = None
    _rects: list[Rect] = PrivateAttr(default_factory=list)

    @field_validator("effects", mode="before")
    @classmethod
    def _coerce_effects(cls, value: object) -> list[EffectInstance]:
        if value is None:
            return []
        if not isinstance(value, list):
            return []
        if value and all(isinstance(item, EffectInstance) for item in value):
            return list(value)
        return deserialize_effects(value)

    @model_validator(mode="after")
    def _validate_effects(self) -> TrackClip:
        validate_effect_chain(self.effects)
        return self

    def _ensure_rects(self, ctx: PrepareContext) -> None:
        self._validate_clips()
        track = Rect(0, 0, ctx.job.width, ctx.job.height)
        self._rects = self.layout.compute(track, len(self.clips))

    async def ensure_layout(self, ctx: PrepareContext) -> None:
        """Compute layout rects only (no ``clip.prepare``).

        Used in the parent process when ``parallelism=multi`` — workers run
        full :meth:`prepare` on their own deserialized job copies.
        """
        self._ensure_rects(ctx)

    async def prepare(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        self._ensure_rects(ctx)
        if not self.enabled:
            return
        from pixfabrica_core.clips.visual import VisualClip

        async def _prepare_clip(clip: Clip, rect: Rect) -> None:
            await clip.prepare(ctx, rect)
            if isinstance(clip, VisualClip):
                await asyncio.gather(
                    *[
                        fx.prepare(replace(ctx, parent_clip=clip), rect)
                        for fx in clip.effects
                        if fx.enabled
                    ]
                )

        track_rect = Rect(0, 0, ctx.job.width, ctx.job.height)
        await asyncio.gather(
            *[
                _prepare_clip(clip, rect)
                for clip, rect in zip(self.clips, self._rects, strict=True)
                if clip.enabled
            ],
            *[
                fx.prepare(replace(ctx, parent_clip=self), track_rect)
                for fx in self.effects
                if fx.enabled
            ],
        )

    def _validate_clips(self) -> None:
        for clip in self.clips:
            if getattr(clip, "backend", None) != self.backend:
                raise TypeError(
                    f"{type(self).__name__} requires {self.backend} clip types, got {type(clip).__name__}"
                )


class SkiaTrack(TrackClip):
    """Track rendered with Skia (2D: text, shapes, waveforms)."""

    clip_type: ClassVar[str] = "std-skia-track"
    backend: ClassVar[str] = "skia"


class GLTrack(TrackClip):
    """Track rendered with ModernGL (GPU: shaders, video, particles).

    Full-frame ``GLPostProcessClip`` effects belong on :class:`GLEffectTrack`
    (``std-post-track``), not here — this track never receives ``source_texture``.
    """

    clip_type: ClassVar[str] = "std-gl-track"
    backend: ClassVar[str] = "gl"

    def _validate_clips(self) -> None:
        from pixfabrica_core.clips.visual import GLPostProcessClip

        super()._validate_clips()
        for clip in self.clips:
            if isinstance(clip, GLPostProcessClip):
                raise ValueError(
                    f"{type(self).__name__} cannot contain GLPostProcessClip ({type(clip).__name__}). "
                    "Use GLEffectTrack (std-post-track) for full-frame post effects."
                )

    @model_validator(mode="after")
    def _validate_gl_track_clips(self) -> GLTrack:
        self._validate_clips()
        return self


class GLEffectTrack(TrackClip):
    """GPU track for a single full-frame post-process pass (``GLPostProcessClip``).

    Serializes as ``std-post-track`` — one row in the web timeline maps 1:1 to
    this type. At most **one** child clip; it must be a :class:`GLPostProcessClip`.
    """

    clip_type: ClassVar[str] = "std-post-track"
    backend: ClassVar[str] = "gl"

    def _validate_clips(self) -> None:
        from pixfabrica_core.clips.visual import GLPostProcessClip

        super()._validate_clips()
        if len(self.clips) > 1:
            raise ValueError(
                f"{type(self).__name__} allows at most one clip; got {len(self.clips)}"
            )
        for clip in self.clips:
            if not isinstance(clip, GLPostProcessClip):
                raise ValueError(
                    f"{type(self).__name__} only accepts GLPostProcessClip, got {type(clip).__name__}"
                )

    @model_validator(mode="after")
    def _validate_gleffect_clips(self) -> GLEffectTrack:
        self._validate_clips()
        if self.effects:
            raise ValueError(
                f"{type(self).__name__} does not support track-level effects; "
                "use a Skia or GL content track instead."
            )
        return self
