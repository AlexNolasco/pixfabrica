from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from pixfabrica_core.audio.bus import AudioBusFrame, AudioTimeline, resolve_bus_frame_for_select
from pixfabrica_core.clips.base import (
    Clip,
    ClipCategory,
    JobInfo,
    TimeState,
)
from pixfabrica_core.graphics import Rect

if TYPE_CHECKING:
    pass

MAX_NODE_EFFECTS = 3

EffectBackend = Literal["gl", "skia", "raster"]


class EffectContext(BaseModel):
    """Per-frame context for image→image effect plugins."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    job: JobInfo
    time: TimeState
    bounds: Rect
    source: Any
    target: Any
    audio_bus_frame: AudioBusFrame = Field(default_factory=AudioBusFrame.zero)
    # Map output UV (0–1) into ``source`` texture UV when source is a padded offscreen.
    src_uv_scale: tuple[float, float] = (1.0, 1.0)
    src_uv_bias: tuple[float, float] = (0.0, 0.0)
    log: logging.Logger = Field(default_factory=lambda: logging.getLogger("pixfabrica.effects"))


class EffectInstance(Clip):
    """Base for per-clip effect plugins attached via ``VisualClip.effects``."""

    effect_type: ClassVar[str] = ""
    clip_category: ClassVar[ClipCategory] = ClipCategory.EFFECTS
    effect_backend: ClassVar[EffectBackend] = "skia"
    singleton: ClassVar[bool] = False
    skip_in_preview: ClassVar[bool] = False

    def apply(self, _ctx: EffectContext) -> None:
        raise NotImplementedError(f"{self.__class__.__name__} must implement apply()")


class GLEffect(EffectInstance):
    """GPU effect — texture ping-pong in ModernGL."""

    effect_backend: ClassVar[EffectBackend] = "gl"
    # Max UV displacement (fraction of texture width/height) this effect may need.
    uv_margin: ClassVar[float] = 0.0


class SkiaEffect(EffectInstance):
    """CPU/Skia effect — surface ping-pong."""

    effect_backend: ClassVar[EffectBackend] = "skia"


class RasterEffect(EffectInstance):
    """Raster / inference effect — numpy or tensor interchange."""

    effect_backend: ClassVar[EffectBackend] = "raster"
    singleton: ClassVar[bool] = True
    skip_in_preview: ClassVar[bool] = True


def effect_supports_bus(fx: EffectInstance) -> bool:
    """True when the effect schema declares an optional ``bus_select`` override."""
    return "bus_select" in fx.__class__.model_fields


def effect_bus_active(fx: EffectInstance) -> bool:
    """Whether the effect pipeline should resolve audio for this effect."""
    if not effect_supports_bus(fx):
        return False
    if "sensitivity" in fx.__class__.model_fields:
        return float(getattr(fx, "sensitivity", 0.0)) > 0.0
    return True


def resolve_effect_bus_select(
    fx: EffectInstance,
    parent: Clip | None,
) -> str | None:
    """Effect override when set, otherwise inherit from the parent visual clip."""
    if effect_supports_bus(fx):
        raw = getattr(fx, "bus_select", None)
        if isinstance(raw, str) and raw.strip():
            return raw
    if parent is not None:
        from pixfabrica_core.audio.mixin import AudioVisualMixin

        if isinstance(parent, AudioVisualMixin):
            return parent.bus_select
    return None


def resolve_effect_audio_bus_frame(
    audio: AudioTimeline,
    parent: Clip | None,
    fx: EffectInstance,
    frame: int,
    *,
    parent_frame: AudioBusFrame,
) -> AudioBusFrame:
    """Per-effect bus frame; falls back to ``parent_frame`` when the effect is bus-inert."""
    if not effect_bus_active(fx):
        return parent_frame
    return resolve_bus_frame_for_select(audio, resolve_effect_bus_select(fx, parent), frame)


def enabled_effects(effects: list[EffectInstance]) -> list[EffectInstance]:
    return [fx for fx in effects if fx.enabled]


def clip_has_enabled_effects(effects: list[EffectInstance]) -> bool:
    return any(fx.enabled for fx in effects)


def track_has_enabled_effects(effects: list[EffectInstance]) -> bool:
    return clip_has_enabled_effects(effects)


def gl_effect_uv_margin(fx: EffectInstance) -> float:
    """Conservative UV headroom for one enabled GL effect instance."""
    import math

    margin = float(getattr(type(fx), "uv_margin", 0.0))
    amp = getattr(fx, "amplitude", None)
    if isinstance(amp, (int, float)):
        # Float: peak |bob| from origin is up to 2× amplitude on the sine swing.
        margin = max(margin, float(amp) * 2.0)
    tilt = getattr(fx, "tilt", None)
    if isinstance(tilt, (int, float)):
        # Sway: peak |sx| ~ 2 on the infinity path; rotation adds corner reach.
        rot = math.radians(float(tilt)) * 2.0
        corner = 0.5 * math.hypot(math.sin(rot), 1.0 - math.cos(rot))
        margin = max(margin, 0.045 + corner)
    return margin


def track_gl_overscan_fraction(effects: list[EffectInstance]) -> float:
    """Padding fraction (per side) required before track GL displacement effects."""
    margin = 0.0
    for fx in enabled_effects(effects):
        if isinstance(fx, GLEffect):
            margin = max(margin, gl_effect_uv_margin(fx))
    return margin


def set_gl_src_uv_uniforms(prog: Any, ctx: EffectContext) -> None:
    """Write optional ``u_src_scale`` / ``u_src_bias`` for padded track sources."""
    if "u_src_scale" in prog:
        member = prog["u_src_scale"]
        if hasattr(member, "value"):
            member.value = ctx.src_uv_scale
    if "u_src_bias" in prog:
        member = prog["u_src_bias"]
        if hasattr(member, "value"):
            member.value = ctx.src_uv_bias


def validate_effect_chain(effects: list[EffectInstance]) -> None:
    """Enforce max length and homogeneous backend among enabled effects."""
    if len(effects) > MAX_NODE_EFFECTS:
        raise ValueError(f"At most {MAX_NODE_EFFECTS} effects per clip; got {len(effects)}")

    active = enabled_effects(effects)
    if not active:
        return

    backends = {type(fx).effect_backend for fx in active}
    if len(backends) > 1:
        raise ValueError(
            "Effect chain must be homogeneous (all gl, all skia, or all raster); "
            f"got backends: {sorted(backends)}"
        )
