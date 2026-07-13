"""Bounds-local Skia blur — optional bass-reactive pulse via sensitivity."""

from __future__ import annotations

from typing import ClassVar

import numpy as np
import skia
from pydantic import Field, PrivateAttr

from pixfabrica_core.audio.bus import AudioBusFrame, bus_timeline_for_select
from pixfabrica_core.clips import ClipCategory, ClipTag, PrepareContext
from pixfabrica_core.composition.effect_def import (
    EffectContext,
    SkiaEffect,
    resolve_effect_bus_select,
)
from pixfabrica_core.graphics import Rect


def _normalize_bus_scalar(raw: np.ndarray) -> np.ndarray:
    """Stretch a bus scalar timeline to ~0..1 using robust job-wide percentiles."""
    if raw.size == 0:
        return raw
    lo, hi = np.percentile(raw, (5.0, 95.0))
    span = max(float(hi - lo), 1e-6)
    return np.clip((raw - lo) / span, 0.0, 1.0).astype(np.float32)


_ATTACK_CAP = 0.2  # fast-rise ceiling; `smoothing` still governs decay (and attack when lower)


def _ema_bass_timeline(
    normalized: np.ndarray,
    total: int,
    n_bus: int,
    *,
    smoothing: float,
) -> np.ndarray:
    """Fast-attack / slow-release envelope: rises quickly on a hit, decays at `smoothing`.

    A single symmetric EMA can't track short percussive bass hits — by the time it
    rises toward the peak the hit has already decayed, so the envelope never leaves
    a narrow low band. Using a fast attack and a slower release (like a compressor's
    envelope follower) lets each hit register near its true peak while still smoothing
    the decay between hits. Attack is capped at ``_ATTACK_CAP`` but never exceeds
    ``smoothing`` itself, so ``smoothing=0`` still means fully raw/instant tracking.
    """
    history = np.zeros(max(total, 0), dtype=np.float32)
    if total <= 0 or normalized.size == 0:
        return history
    release = float(smoothing)
    attack = min(release, _ATTACK_CAP)
    one_minus_attack = 1.0 - attack
    one_minus_release = 1.0 - release
    acc = 0.0
    for f in range(total):
        target = float(normalized[f]) if f < n_bus else 0.0
        if target > acc:
            acc = acc * attack + target * one_minus_attack
        else:
            acc = acc * release + target * one_minus_release
        history[f] = acc
    return history


class BlurSkia(SkiaEffect):
    """Gaussian blur applied to a single clip's output."""

    effect_type: ClassVar[str] = "std-blur-skia"
    clip_category: ClassVar[ClipCategory] = ClipCategory.EFFECTS
    clip_tags: ClassVar[list[str]] = [ClipTag.AUDIO_REACTIVE]

    bus_select: str | None = Field(
        default=None,
        description="Bus for bass reactivity when sensitivity > 0; inherits parent bus when unset",
    )
    radius: float = Field(
        default=4.0,
        ge=0.0,
        le=64.0,
        multiple_of=0.01,
        description="Static blur sigma; when sensitivity > 0 this is the sigma at full bass instead",
    )
    sensitivity: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="0 = static blur at radius; >0 = blur scales from 0 at silence up to "
        "radius * (1 + sensitivity) at full bass",
    )
    smoothing: float = Field(
        default=0.85,
        ge=0.0,
        le=0.9,
        multiple_of=0.05,
        description="Temporal smoothing of normalized bass (0 = raw, 0.9 = sluggish)",
    )

    _smoothed_bass: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype=np.float32))

    async def prepare(self, ctx: PrepareContext, _bounds: Rect | None = None) -> None:
        self._smoothed_bass = self._build_smoothed_bass(ctx)

    def _build_smoothed_bass(self, ctx: PrepareContext) -> np.ndarray:
        total = max(ctx.job.total_frames, 0)
        if self.sensitivity <= 0.0 or total == 0:
            return np.zeros(0, dtype=np.float32)

        frames: list[AudioBusFrame] | None = bus_timeline_for_select(
            ctx.audio,
            resolve_effect_bus_select(self, ctx.parent_clip),
        )
        if not frames:
            return np.zeros(0, dtype=np.float32)

        n_bus = min(total, len(frames))
        raw = np.asarray([float(frames[f].bass) for f in range(n_bus)], dtype=np.float32)
        return _ema_bass_timeline(
            _normalize_bus_scalar(raw),
            total,
            n_bus,
            smoothing=float(self.smoothing),
        )

    def _bass_for_frame(self, ctx: EffectContext) -> float:
        if self._smoothed_bass.size:
            f = max(0, min(ctx.time.frame, self._smoothed_bass.shape[0] - 1))
            return float(self._smoothed_bass[f])
        return float(np.clip(ctx.audio_bus_frame.bass, 0.0, 1.0))

    def _effective_radius(self, ctx: EffectContext) -> float:
        if self.radius <= 0.0:
            return 0.0
        if self.sensitivity <= 0.0:
            return self.radius

        bass = self._bass_for_frame(ctx)
        # 0 at silence; up to radius * (1 + sensitivity) at full bass.
        return self.radius * (1.0 + self.sensitivity) * bass

    def apply(self, ctx: EffectContext) -> None:
        radius = self._effective_radius(ctx)
        if radius <= 0.0:
            image = ctx.source.makeImageSnapshot()
            ctx.target.getCanvas().drawImage(image, 0, 0)
            return
        image = ctx.source.makeImageSnapshot()
        paint = skia.Paint()
        paint.setImageFilter(skia.ImageFilters.Blur(radius, radius))
        canvas = ctx.target.getCanvas()
        canvas.clear(skia.ColorTRANSPARENT)
        canvas.drawImage(image, 0, 0, paint=paint)
