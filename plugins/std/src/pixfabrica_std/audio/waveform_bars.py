from __future__ import annotations

import hashlib
import math
from typing import ClassVar

import numpy as np
import skia
from pydantic import Field, PrivateAttr

from pixfabrica_core.audio.bus import AudioBusFrame
from pixfabrica_core.audio.mixin import AudioVisualMixin
from pixfabrica_core.clips import ClipCategory, ClipSkia, ClipTag, PrepareContext, RenderContext
from pixfabrica_core.graphics import Rect
from pixfabrica_core.theme.color import Color, ColorToken, color_field, resolve_color

_HARMONIC_COUNT = 3
_HARMONIC_FREQ_MIN = 1.0
_HARMONIC_FREQ_MAX = 4.0
_HARMONIC_SPEED_MIN = 0.3
_HARMONIC_SPEED_MAX = 1.0

_Harmonic = tuple[float, float, float, float]  # freq, phase, amp, angular_speed


def _seed_from_id(clip_id: str) -> int:
    digest = hashlib.sha256(clip_id.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big")


def _cluster_harmonics(seed: int) -> list[_Harmonic]:
    """Seeded sine harmonics driving the cluster shape — fixed for the clip's lifetime,
    but each has its own angular speed so the pattern ripples over time rather than
    freezing whenever the audio amplitude holds steady."""
    rng = np.random.default_rng(seed)
    harmonics: list[_Harmonic] = []
    for _ in range(_HARMONIC_COUNT):
        freq = float(rng.uniform(_HARMONIC_FREQ_MIN, _HARMONIC_FREQ_MAX))
        phase = float(rng.uniform(0.0, 2.0 * math.pi))
        amp = float(rng.uniform(0.5, 1.0))
        speed = float(rng.uniform(_HARMONIC_SPEED_MIN, _HARMONIC_SPEED_MAX))
        if rng.uniform(-1.0, 1.0) < 0.0:
            speed = -speed
        harmonics.append((freq, phase, amp, speed))
    return harmonics


def _cluster_row(x: np.ndarray, harmonics: list[_Harmonic], t: float) -> np.ndarray:
    """Evaluate the rippling cluster profile at time ``t`` (seconds), normalized to 0..1
    via each harmonic's fixed amplitude bound — no per-frame min/max, so the pattern
    drifts smoothly instead of snapping its peak back to 1.0 every frame."""
    raw = np.zeros_like(x, dtype=np.float64)
    total_amp = 0.0
    for freq, phase, amp, speed in harmonics:
        raw += amp * np.sin(2.0 * np.pi * freq * x + phase + speed * t)
        total_amp += amp
    if total_amp <= 1e-8:
        return np.zeros_like(x, dtype=np.float32)
    profile = (raw + total_amp) / (2.0 * total_amp)
    return np.clip(profile, 0.0, 1.0).astype(np.float32)


def _normalize_amplitude_timeline(frames: list[AudioBusFrame], n: int) -> np.ndarray:
    if n <= 0:
        return np.zeros(0, dtype=np.float32)
    raw = np.asarray([float(frames[f].amplitude) for f in range(n)], dtype=np.float32)
    lo, hi = np.percentile(raw, (5.0, 95.0))
    span = max(float(hi - lo), 1e-6)
    return np.clip((raw - lo) / span, 0.0, 1.0).astype(np.float32)


class WaveformBars(AudioVisualMixin, ClipSkia):
    """Audio-reactive equalizer: a rippling cluster of mirrored bars pulsing with amplitude."""

    clip_type: ClassVar[str] = "std-waveform-bars"
    clip_category: ClassVar[ClipCategory] = ClipCategory.AUDIO
    clip_tags: ClassVar[list[str]] = [
        ClipTag.AUDIO_REACTIVE,
        ClipTag.ANIMATED,
        ClipTag.GLOW,
    ]

    color: ColorToken | Color = color_field(ColorToken.ACCENT)
    glow_color: ColorToken | Color | None = Field(
        default=None,
        json_schema_extra={"widget": "color"},
        description="Glow halo color; defaults to bar color when unset",
    )
    glow: float = Field(
        default=0.0,
        ge=0.0,
        le=10.0,
        multiple_of=1.0,
        description="Glow blur sigma in pixels",
    )
    opacity: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        multiple_of=0.05,
        description="Bar opacity",
    )
    bar_count: int = Field(
        default=5,
        ge=4,
        le=96,
        multiple_of=1,
        description="Number of mirrored bars across the strip",
    )
    bar_width: float = Field(
        default=7.0,
        ge=0.0,
        le=64.0,
        multiple_of=1.0,
        description="Bar width in pixels; 0 hides the bars entirely",
    )
    width: float = Field(
        default=15.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.05,
        description="Overall strip width as a fraction of bounds width, centered horizontally; 0 hides the bars entirely",
    )
    offset_y: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Center line position as a fraction of bounds height",
    )
    max_bar_height: float = Field(
        default=0.15,
        ge=0.05,
        le=1.0,
        multiple_of=0.05,
        description="Maximum half-extent (above or below center) as a fraction of bounds height",
    )
    min_bar_height: float = Field(
        default=0.03,
        ge=0.0,
        le=0.5,
        multiple_of=0.01,
        description="Minimum half-extent so quiet passages still show a small dot",
    )
    sensitivity: float = Field(
        default=2.5,
        ge=0.1,
        le=8.0,
        multiple_of=0.1,
        description="Audio response gain on amplitude after job-wide normalization",
    )
    smoothing: float = Field(
        default=0.3,
        ge=0.0,
        le=0.9,
        multiple_of=0.05,
        description="Temporal smoothing of amplitude per frame (0=raw, 0.9=sluggish)",
    )
    motion_speed: float = Field(
        default=1.0,
        ge=0.0,
        le=5.0,
        multiple_of=0.1,
        description="Speed at which the bar cluster ripples over time (0=frozen shape, higher=livelier motion)",
    )

    _cluster_history: np.ndarray = PrivateAttr(
        default_factory=lambda: np.zeros((0, 0), dtype=np.float32)
    )
    _amplitude_history: np.ndarray = PrivateAttr(
        default_factory=lambda: np.zeros(0, dtype=np.float32)
    )
    _bar_paint: skia.Paint = PrivateAttr()
    _glow_paint: skia.Paint | None = PrivateAttr(default=None)

    async def prepare(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        self._cluster_history = self._build_cluster_history(ctx)
        self._amplitude_history = self._build_amplitude_history(ctx)

        sr, sg, sb, _ = resolve_color(self.color, ctx.job.colors).rgba
        self._bar_paint = skia.Paint(AntiAlias=True)
        self._bar_paint.setColor4f(skia.Color4f(sr, sg, sb, self.opacity))

        glow_src = self.glow_color if self.glow_color is not None else self.color
        gr, gg, gb, _ = resolve_color(glow_src, ctx.job.colors).rgba
        if self.glow > 0:
            glow_sigma = ctx.job.scale_output_px(self.glow)
            glow_paint = skia.Paint(AntiAlias=True)
            glow_paint.setColor4f(skia.Color4f(gr, gg, gb, min(1.0, self.opacity * 0.9)))
            glow_paint.setImageFilter(skia.ImageFilters.Blur(glow_sigma, glow_sigma))
            self._glow_paint = glow_paint
        else:
            self._glow_paint = None

    def _build_cluster_history(self, ctx: PrepareContext) -> np.ndarray:
        n = self.bar_count
        total = max(ctx.job.total_frames, 0)
        history = np.zeros((total, n), dtype=np.float32)
        if total == 0 or n <= 0:
            return history

        harmonics = _cluster_harmonics(_seed_from_id(self.id))
        x = np.linspace(0.0, 1.0, n, dtype=np.float64)
        fps = max(float(ctx.job.fps), 1e-6)
        motion = float(self.motion_speed)
        for f in range(total):
            t = (f / fps) * motion
            history[f] = _cluster_row(x, harmonics, t)
        return history

    def _build_amplitude_history(self, ctx: PrepareContext) -> np.ndarray:
        total = max(ctx.job.total_frames, 0)
        history = np.zeros(total, dtype=np.float32)
        if total == 0:
            return history

        frames = self.bus_timeline(ctx)
        if not frames:
            return history

        n = min(total, len(frames))
        normalized = _normalize_amplitude_timeline(frames, n)
        s = float(self.smoothing)
        one_minus_s = 1.0 - s
        prev = 0.0
        for f in range(total):
            level = float(normalized[f]) if f < n else 0.0
            prev = prev * s + level * one_minus_s
            history[f] = prev
        return history

    def _current_cluster(self, ctx: RenderContext) -> np.ndarray:
        if self._cluster_history.shape[0] == 0:
            return np.zeros(self.bar_count, dtype=np.float32)
        idx = max(0, min(ctx.time.frame, self._cluster_history.shape[0] - 1))
        return self._cluster_history[idx]

    def _current_level(self, ctx: RenderContext) -> float:
        if self._amplitude_history.size:
            idx = max(0, min(ctx.time.frame, self._amplitude_history.shape[0] - 1))
            level = float(self._amplitude_history[idx])
        else:
            level = float(ctx.audio_bus_frame.amplitude)
        return self.scale_audio(level)

    def draw(self, ctx: RenderContext) -> None:
        n = self.bar_count
        if n <= 0 or self.bar_width <= 0.0 or self.width <= 0.0:
            return

        bnd = ctx.bounds
        w, h = float(bnd.width), float(bnd.height)
        center_y = bnd.y + self.offset_y * h
        min_half = self.min_bar_height * h
        max_half = self.max_bar_height * h

        level = self._current_level(ctx)
        cluster = self._current_cluster(ctx)

        strip_w = w * self.width
        strip_x = bnd.x + (w - strip_w) / 2.0
        slot_w = strip_w / float(n)
        radius = ctx.job.scale_output_px(self.bar_width) / 2.0

        canvas: skia.Canvas = ctx.canvas
        canvas.save()
        canvas.clipRect(skia.Rect.MakeXYWH(bnd.x, bnd.y, w, h))

        for i in range(n):
            half = min_half + (max_half - min_half) * float(cluster[i]) * level
            if half <= 0.0:
                continue
            cx = strip_x + (i + 0.5) * slot_w
            rect = skia.Rect.MakeLTRB(cx - radius, center_y - half, cx + radius, center_y + half)
            rrect = skia.RRect()
            rrect.setRectXY(rect, radius, radius)
            if self._glow_paint is not None:
                canvas.drawRRect(rrect, self._glow_paint)
            canvas.drawRRect(rrect, self._bar_paint)

        canvas.restore()
