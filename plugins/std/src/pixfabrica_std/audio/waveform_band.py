from __future__ import annotations

import math
from typing import ClassVar

import numpy as np
import skia
from pydantic import Field, PrivateAttr

from pixfabrica_core.audio.bus import N_SPECTRUM, AudioBusFrame
from pixfabrica_core.audio.mixin import AudioVisualMixin
from pixfabrica_core.clips import ClipCategory, ClipSkia, ClipTag, PrepareContext, RenderContext
from pixfabrica_core.graphics import Rect
from pixfabrica_core.theme.color import Color, ColorToken, color_field, resolve_color
from pixfabrica_std.tilt import (
    ANGLE_BAND_DESC,
    ANGLE_BAND_SKEW_MAX,
    ANGLE_BAND_SKEW_MIN,
    band_left_center_y,
    band_skew_px,
)


class WaveformBand(AudioVisualMixin, ClipSkia):
    """Audio-reactive oscillating waveform line clipped to a tilted horizontal band."""

    clip_type: ClassVar[str] = "std-waveform-band"
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
        description="Glow halo color; defaults to stroke color when unset",
    )
    glow: float = Field(
        default=0.0,
        ge=0.0,
        le=64.0,
        multiple_of=1.0,
        description="Glow blur sigma in pixels",
    )
    line_width: float = Field(
        default=1.5,
        ge=0.5,
        le=16.0,
        multiple_of=0.5,
        description="Stroke width in pixels",
    )
    offset_y: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Band center as fraction of bounds height",
    )
    band_height: float = Field(
        default=0.2,
        ge=0.01,
        le=1.0,
        multiple_of=0.01,
        description="Band thickness as fraction of bounds height",
    )
    angle: float = Field(
        default=-0.0,
        ge=ANGLE_BAND_SKEW_MIN,
        le=ANGLE_BAND_SKEW_MAX,
        multiple_of=1.0,
        description=ANGLE_BAND_DESC,
    )
    opacity: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        multiple_of=0.05,
        description="Stroke opacity",
    )
    sensitivity: float = Field(
        default=2.5,
        ge=0.1,
        le=8.0,
        multiple_of=0.1,
        description="Audio response gain on spectrum shape and amplitude drive",
    )
    wave_freq: float = Field(
        default=14.0,
        ge=1.0,
        le=40.0,
        multiple_of=1.0,
        description="Sine carrier cycles across full band width (try ~20 for denser ripples)",
    )
    focus: float = Field(
        default=1.0,
        ge=1.0,
        le=4.0,
        multiple_of=0.25,
        description="Pull motion toward the center; 1 = full width, higher = calmer edges",
    )
    bin_start: int = Field(
        default=5,
        ge=0,
        le=56,
        multiple_of=1,
        description="First spectrum band at band center; raise to skip sub-bass dead zones",
    )
    smoothing: float = Field(
        default=0.05,
        ge=0.0,
        le=0.9,
        multiple_of=0.05,
        description="Temporal smoothing of spectrum bands per frame (0=raw, 0.9=sluggish)",
    )

    _clip_path: skia.Path = PrivateAttr()
    _skew_px: float = PrivateAttr(default=0.0)
    _band_top_l: float = PrivateAttr(default=0.0)
    _band_bot_l: float = PrivateAttr(default=0.0)
    _canvas_w: float = PrivateAttr(default=0.0)
    _nx: float = PrivateAttr(default=0.0)
    _ny: float = PrivateAttr(default=1.0)
    _wave_amp: float = PrivateAttr(default=0.0)
    _smoothed_freq: np.ndarray = PrivateAttr(
        default_factory=lambda: np.zeros((0, N_SPECTRUM), dtype=np.float32)
    )
    _stroke_paint: skia.Paint = PrivateAttr()
    _glow_paint: skia.Paint | None = PrivateAttr(default=None)

    async def prepare(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        b = bounds or Rect(0, 0, ctx.job.width, ctx.job.height)
        w, h = float(b.width), float(b.height)
        self._canvas_w = w

        skew = band_skew_px(w, -self.angle)
        center_y = band_left_center_y(h, self.offset_y, skew)
        half_h = (self.band_height / 2) * h

        pts = [
            (0.0, center_y - half_h),
            (w, center_y - half_h - skew),
            (w, center_y + half_h - skew),
            (0.0, center_y + half_h),
        ]

        self._skew_px = pts[0][1] - pts[1][1]
        self._band_top_l = pts[0][1]
        self._band_bot_l = pts[3][1]
        half_band_h = self._band_bot_l - self._band_top_l
        diag_len = math.sqrt(w * w + self._skew_px * self._skew_px)
        if diag_len > 0:
            self._nx = self._skew_px / diag_len
            self._ny = w / diag_len
            tilt_scale = w / diag_len
        else:
            self._nx = 0.0
            self._ny = 1.0
            tilt_scale = 1.0
        self._wave_amp = half_band_h * 0.5 * 0.85 * tilt_scale

        self._clip_path = skia.Path()
        self._clip_path.moveTo(*pts[0])
        for p in pts[1:]:
            self._clip_path.lineTo(*p)
        self._clip_path.close()

        self._smoothed_freq = self._build_smoothed_timeline(ctx)

        sr, sg, sb, _ = resolve_color(self.color, ctx.job.colors).rgba
        self._stroke_paint = skia.Paint(AntiAlias=True)
        self._stroke_paint.setStyle(skia.Paint.kStroke_Style)
        self._stroke_paint.setStrokeCap(skia.Paint.kRound_Cap)
        self._stroke_paint.setStrokeJoin(skia.Paint.kRound_Join)
        self._stroke_paint.setStrokeWidth(self.line_width)
        self._stroke_paint.setColor4f(skia.Color4f(sr, sg, sb, self.opacity))

        glow_src = self.glow_color if self.glow_color is not None else self.color
        gr, gg, gb, _ = resolve_color(glow_src, ctx.job.colors).rgba
        if self.glow > 0:
            glow_paint = skia.Paint(AntiAlias=True)
            glow_paint.setStyle(skia.Paint.kStroke_Style)
            glow_paint.setStrokeCap(skia.Paint.kRound_Cap)
            glow_paint.setStrokeJoin(skia.Paint.kRound_Join)
            glow_paint.setStrokeWidth(self.line_width * 3.0)
            glow_paint.setColor4f(skia.Color4f(gr, gg, gb, 0.7))
            glow_paint.setImageFilter(skia.ImageFilters.Blur(self.glow, self.glow))
            self._glow_paint = glow_paint
        else:
            self._glow_paint = None

    def _build_smoothed_timeline(self, ctx: PrepareContext) -> np.ndarray:
        total = max(ctx.job.total_frames, 0)
        history = np.zeros((total, N_SPECTRUM), dtype=np.float32)
        if total == 0:
            return history

        frames: list[AudioBusFrame] | None = self.bus_timeline(ctx)
        if not frames:
            return history

        s = float(self.smoothing)
        one_minus_s = 1.0 - s
        prev = np.zeros(N_SPECTRUM, dtype=np.float32)
        for f in range(total):
            if f >= len(frames):
                prev = prev * s
            else:
                prev = prev * s + np.asarray(frames[f].spectrum, dtype=np.float32) * one_minus_s
            history[f] = prev
        return history

    def _compute_wave_xy(
        self,
        data: np.ndarray,
        *,
        amplitude: float = 0.0,
    ) -> tuple[np.ndarray, np.ndarray]:
        w = int(self._canvas_w)
        xs = np.arange(w + 1, dtype=np.float32)
        half = w / 2.0
        d = np.abs(xs - half) / half if half > 0 else np.zeros_like(xs)

        spec = np.asarray(data, dtype=np.float32)
        peak = float(spec.max())
        if peak > 1e-8:
            spec = spec / peak

        n = spec.shape[0]
        max_idx = float(max(n - 1, 0))
        bin_lo = float(min(self.bin_start, max(n - 1, 0)))
        bin_f = bin_lo + d * (max_idx - bin_lo)
        bin_i = np.floor(bin_f).astype(np.int64)
        bin_i = np.clip(bin_i, 0, max(n - 2, 0))
        frac = bin_f - bin_i
        v0 = spec[bin_i]
        v1 = spec[np.minimum(bin_i + 1, n - 1)]
        raw = (v0 * (1.0 - frac) + v1 * frac) * float(self.sensitivity)
        env = np.clip(raw, 0.0, 1.0) * self.scale_audio(max(amplitude, peak))
        carrier = np.cos(2.0 * np.pi * self.wave_freq * d)
        weight = np.ones_like(d) if self.focus <= 1.0 else 1.0 - np.power(d, 1.0 / self.focus)

        band_mid = (self._band_top_l + self._band_bot_l) * 0.5
        skew_per_x = self._skew_px / w if w > 0 else 0.0
        cy = band_mid - skew_per_x * xs
        offset = carrier * env * self._wave_amp * weight
        return xs + offset * self._nx, cy + offset * self._ny

    def draw(self, ctx: RenderContext) -> None:
        frame = ctx.time.frame
        if self._smoothed_freq.size:
            idx = max(0, min(frame, self._smoothed_freq.shape[0] - 1))
            data = self._smoothed_freq[idx]
        else:
            af = ctx.audio_bus_frame
            data = np.asarray(af.spectrum, dtype=np.float32)

        wave_x, wave_y = self._compute_wave_xy(
            data,
            amplitude=float(ctx.audio_bus_frame.amplitude),
        )
        w = int(self._canvas_w)

        path = skia.Path()
        path.moveTo(float(wave_x[0]), float(wave_y[0]))
        for i in range(1, w + 1):
            path.lineTo(float(wave_x[i]), float(wave_y[i]))

        canvas: skia.Canvas = ctx.canvas
        b = ctx.bounds
        canvas.save()
        canvas.translate(b.x, b.y)
        canvas.clipPath(self._clip_path, skia.ClipOp.kIntersect, True)

        if self._glow_paint is not None:
            canvas.drawPath(path, self._glow_paint)
        canvas.drawPath(path, self._stroke_paint)
        canvas.restore()
