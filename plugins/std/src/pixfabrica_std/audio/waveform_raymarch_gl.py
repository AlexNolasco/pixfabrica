from __future__ import annotations

from typing import Any, ClassVar

import moderngl
import numpy as np
from pydantic import Field, PrivateAttr

from pixfabrica_core.audio.bus import N_SPECTRUM, AudioBusFrame
from pixfabrica_core.audio.mixin import AudioVisualMixin
from pixfabrica_core.clips import ClipCategory, ClipGL, ClipTag, PrepareContext, RenderContext
from pixfabrica_core.graphics import Rect
from pixfabrica_core.theme.color import Color, ColorToken, color_field, resolve_color

# Octave step sizes from the sine-wave stack — must match the shader's OCTAVE_D array.
_N_BANDS = 5

_VERT = """
#version 330 core
in vec2 in_vert;
void main() { gl_Position = vec4(in_vert, 0.0, 1.0); }
"""

_FRAG = """
#version 330 core

uniform vec2  u_res;
uniform vec2  u_origin;
uniform float u_canvas_h;

uniform float u_time;
uniform float u_pan_y;
uniform float u_brightness;
uniform float u_brightness_gain;
uniform float u_level;
uniform vec3  u_color;
uniform float u_colorize;
uniform float u_luma_alpha;
uniform float u_punch;
uniform int   u_steps;
uniform float u_band_gain[5];

out vec4 frag_color;

const float OCTAVE_D[5] = float[5](1.0, 2.0, 4.0, 8.0, 16.0);

void main() {
    float px = gl_FragCoord.x - u_origin.x;
    float py = (u_canvas_h - gl_FragCoord.y) - u_origin.y;
    // u_pan_y shifts the whole rendered scene vertically; the floor plane below
    // (fixed at 1.0) never moves — only what the camera frames does.
    vec2 fragCoord = vec2(px, u_res.y - py + u_pan_y);

    // Focal length is based on the shorter of width/height so portrait canvases keep
    // a full field of view horizontally instead of being cropped by a height-only basis.
    float focal = min(u_res.x, u_res.y);

    // Beat punch narrows the FOV (zoom-in) instead of only nudging geometry —
    // a screen-space camera effect reads far more clearly than SDF-buried amplitude.
    vec3 rayDir = normalize(vec3(2.0 * fragCoord - u_res, -focal * (1.0 + u_punch * 0.2)));

    vec4 O = vec4(0.0);
    float z = 0.0;

    for (int i = 0; i < u_steps; i++) {
        vec3 p = z * rayDir;
        p += vec3(1.0, 1.0, 1.0);

        float r = max(-p.y, 0.0);
        p.y += r + r;

        for (int oct = 0; oct < 5; oct++) {
            float d = OCTAVE_D[oct];
            float gain = 1.0 + u_band_gain[oct];
            p.y += cos(p * d + 2.0 * u_time * cos(d) + z).x / d * gain;
        }

        float stepZ = p.z + 3.0;
        stepZ = stepZ > 0.0 ? stepZ : -0.1 * stepZ;
        float d = (0.1 * r + abs(p.y - 1.0) / (1.0 + r + r + r * r) + stepZ) / 8.0;
        z += d;

        O += (cos(z * 0.5 + u_time + vec4(0.0, 2.0, 4.0, 3.0)) + 1.3) / d / z;
    }

    // Blend the original per-channel rainbow (tinted by u_color) with a fully
    // color-locked single hue — u_colorize=0 keeps the rainbow's depth, =1 locks
    // to u_color's hue exactly. Audio level pulses brightness on top.
    float luma = max(max(O.r, O.g), O.b);
    vec3 rainbowTint = O.rgb * u_color;
    vec3 solidTint = luma * u_color;
    vec3 pre = mix(rainbowTint, solidTint, u_colorize);

    float exposure = u_brightness / (1.0 + u_brightness_gain * u_level + u_punch * 1.5);
    vec3 toned = tanh(pre / exposure);

    float alpha = mix(1.0, clamp(max(max(toned.r, toned.g), toned.b), 0.0, 1.0), u_luma_alpha);
    frag_color = vec4(toned * alpha, alpha);
}
"""

_QUAD = np.array([-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0], dtype="f4")

_PEAK_PCT = 90.0
_HEADROOM = 0.9
_SAT_GAIN = 0.6


def _band_ranges(n_bands: int, n_spectrum: int = N_SPECTRUM) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for i in range(n_bands):
        start = i * n_spectrum // n_bands
        end = max(start, (i + 1) * n_spectrum // n_bands - 1)
        ranges.append((start, end))
    return ranges


def _mean_group(freq: np.ndarray, start: int, end: int) -> float:
    if end <= start:
        return float(freq[start])
    return float(freq[start : end + 1].mean())


def _ema_pass(history: np.ndarray, smoothing: float) -> np.ndarray:
    """Single-pole low-pass over a (frame, band) history; each frame updates from the last."""
    out = np.zeros_like(history)
    prev = np.zeros(history.shape[1], dtype="f4")
    one_minus_s = 1.0 - smoothing
    for f in range(history.shape[0]):
        prev = prev * smoothing + history[f] * one_minus_s
        out[f] = prev
    return out


def _shape_bands(row: np.ndarray, sensitivity: float) -> np.ndarray:
    """Map smoothed band levels to per-octave amplitude gain with a soft ceiling."""
    peak = float(np.percentile(row, _PEAK_PCT))
    if peak <= 1e-8:
        return np.zeros_like(row)
    normalized = row / peak
    shaped = np.tanh(normalized * float(sensitivity) * _SAT_GAIN)
    return (shaped * _HEADROOM).astype(np.float32)


class WaveformRaymarchGL(AudioVisualMixin, ClipGL):
    """Raymarched mirrored sine-wave tunnel; each octave of the wave stack reacts to a
    frequency band of the audio bus. Based on "Waveform" by @XorDev (Shadertoy).
    """

    clip_type: ClassVar[str] = "std-waveform-raymarch-gl"
    clip_category: ClassVar[ClipCategory] = ClipCategory.AUDIO
    clip_tags: ClassVar[list[str]] = [
        ClipTag.AUDIO_REACTIVE,
        ClipTag.ANIMATED,
        ClipTag.GL,
    ]

    color: ColorToken | Color = color_field(ColorToken.PRIMARY)
    offset_y: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Vertical position of the whole scene in frame (0.5 = centered, "
        "matching the original framing; 0 = scene near the bottom, 1 = scene near the "
        "top). The reflective floor plane's own geometry stays fixed — only where "
        "the camera frames it in the image moves.",
    )
    speed: float = Field(
        default=1.0,
        ge=0.0,
        le=4.0,
        multiple_of=0.05,
        description="Animation speed multiplier.",
    )
    speed_reactivity: float = Field(
        default=0.5,
        ge=0.0,
        le=2.0,
        multiple_of=0.05,
        description="How much overall audio level speeds up the animation on top of "
        "speed (0 = constant speed, higher = faster swirl when loud).",
    )
    beat_punch: float = Field(
        default=0.6,
        ge=0.0,
        le=2.0,
        multiple_of=0.05,
        description="Strength of the camera zoom-in / brightness flash triggered on "
        "detected beats or onsets (0 = off).",
    )
    brightness: float = Field(
        default=900.0,
        ge=200.0,
        le=3000.0,
        multiple_of=10.0,
        description="Tonemap divisor; lower values brighten the scene.",
    )
    brightness_reactivity: float = Field(
        default=0.4,
        ge=0.0,
        le=2.0,
        multiple_of=0.05,
        description="How much overall audio level brightens the scene on top of the "
        "wave-shape reaction (0 = no brightness pulse, higher = stronger pulse on hits).",
    )
    colorize: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.05,
        description="Blend between the shader's original per-channel rainbow tinted by "
        "color (0) and a single hue fully locked to color (1).",
    )
    luma_alpha: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Alpha derived from output brightness (0 = fully opaque; 1 = alpha "
        "tracks luminance so dark areas turn transparent, for compositing over other layers).",
    )
    quality: int = Field(
        default=90,
        ge=30,
        le=90,
        multiple_of=1,
        description="Raymarch step count; lower values render faster at reduced fidelity.",
    )
    smoothing: float = Field(
        default=0.45,
        ge=0.0,
        le=0.9,
        multiple_of=0.05,
        description="Temporal smoothing on per-octave audio gain, applied as a two-stage "
        "low-pass to damp raymarch jitter (0 = raw, 0.9 = sluggish).",
    )
    sensitivity: float = Field(
        default=5.0,
        ge=0.1,
        le=8.0,
        multiple_of=0.05,
        description="Audio response gain applied to per-octave wave amplitude.",
    )

    _canvas_h: float = PrivateAttr(default=0.0)
    _bounds_x: float = PrivateAttr(default=0.0)
    _bounds_y: float = PrivateAttr(default=0.0)
    _bounds_w: float = PrivateAttr(default=0.0)
    _bounds_h: float = PrivateAttr(default=0.0)

    _program: moderngl.Program | None = PrivateAttr(default=None)
    _vao: moderngl.VertexArray | None = PrivateAttr(default=None)
    _band_history: np.ndarray = PrivateAttr(
        default_factory=lambda: np.zeros((0, _N_BANDS), dtype="f4")
    )
    _time_history: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype="f4"))
    _punch_history: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype="f4"))
    _level_history: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype="f4"))

    async def prepare(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        b = bounds or Rect(0, 0, ctx.job.width, ctx.job.height)
        self._canvas_h = float(ctx.job.height)
        self._bounds_x = float(b.x)
        self._bounds_y = float(b.y)
        self._bounds_w = float(b.width)
        self._bounds_h = float(b.height)
        (
            self._band_history,
            self._time_history,
            self._punch_history,
            self._level_history,
        ) = self._precompute_history(ctx)

    def _precompute_history(
        self, ctx: PrepareContext
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        total = max(ctx.job.total_frames, 0)
        bands_out = np.zeros((total, _N_BANDS), dtype="f4")
        time_out = np.zeros(total, dtype="f4")
        punch_out = np.zeros(total, dtype="f4")
        level_out = np.zeros(total, dtype="f4")
        if total == 0:
            return bands_out, time_out, punch_out, level_out

        frames: list[AudioBusFrame] | None = self.bus_timeline(ctx)
        dt = 1.0 / float(ctx.job.fps) if ctx.job.fps > 0 else 0.0
        base_speed = float(self.speed)

        if not frames:
            time_out = np.arange(total, dtype="f4") * dt * base_speed
            return bands_out, time_out, punch_out, level_out

        ranges = _band_ranges(_N_BANDS)
        sens = float(self.sensitivity)
        n_bus = min(total, len(frames))

        raw_hist = np.zeros((total, _N_BANDS), dtype="f4")
        amp_hist = np.zeros(total, dtype="f4")
        for f in range(total):
            if f < n_bus:
                freq = np.asarray(frames[f].spectrum, dtype="f4")
                raw_hist[f] = [_mean_group(freq, start, end) for start, end in ranges]
                amp_hist[f] = frames[f].amplitude
            elif f > 0:
                raw_hist[f] = raw_hist[f - 1]
                amp_hist[f] = amp_hist[f - 1]

        # Two-stage (critically-damped) EMA: the raymarch amplifies frame-to-frame band
        # jitter into visible jerkiness, so a single-pass filter isn't enough — smoothing
        # the same way twice removes that jitter while staying responsive to real hits.
        smoothed = _ema_pass(raw_hist, float(self.smoothing))
        smoothed = _ema_pass(smoothed, float(self.smoothing))

        for f in range(total):
            bands_out[f] = _shape_bands(smoothed[f], sens)

        # Overall loudness for brightness/speed reactivity comes from the bus's absolute
        # amplitude scalar, not the per-octave bands — those are peak-normalized per frame
        # (relative shape across the 5 octaves), so they read the same whether the bus is
        # quiet or loud and can't drive an "is it loud right now" signal.
        level_out = _ema_pass(amp_hist.reshape(-1, 1), float(self.smoothing)).ravel()
        level_out = _ema_pass(level_out.reshape(-1, 1), float(self.smoothing)).ravel()

        # Integrate an instantaneous speed multiplier into a running "shader time" curve
        # instead of scaling wall-clock time per frame directly — a direct multiply would
        # reintroduce phase jumps (the same jerkiness the band smoothing above fixes).
        speed_mult = base_speed * (1.0 + float(self.speed_reactivity) * level_out)
        time_out = np.concatenate(([0.0], np.cumsum(speed_mult)[:-1])).astype("f4") * dt

        # Beat/onset-triggered punch envelope: instant attack, fast exponential decay —
        # discrete hits read far more clearly than continuous geometry modulation.
        decay = float(np.exp(-dt / 0.15)) if dt > 0 else 0.0
        punch = 0.0
        for f in range(total):
            hit = frames[f].beat or frames[f].onset if f < n_bus else False
            punch = max(1.0 if hit else 0.0, punch * decay)
            punch_out[f] = punch

        return bands_out, time_out, punch_out, level_out

    def _set_uniform(self, prog: moderngl.Program, name: str, value: Any) -> None:
        if name in prog:
            member = prog[name]
            if isinstance(member, moderngl.Uniform):
                member.value = value

    def _set_band_gains(self, prog: moderngl.Program, bands: np.ndarray) -> None:
        if "u_band_gain[0]" in prog:
            for i in range(_N_BANDS):
                self._set_uniform(prog, f"u_band_gain[{i}]", float(bands[i]))
        elif "u_band_gain" in prog:
            member = prog["u_band_gain"]
            if isinstance(member, moderngl.Uniform):
                member.value = tuple(float(bands[i]) for i in range(_N_BANDS))  # type: ignore[assignment]

    def draw(self, ctx: RenderContext) -> None:
        gl: moderngl.Context = ctx.canvas

        if self._program is None:
            self._program = gl.program(vertex_shader=_VERT, fragment_shader=_FRAG)
            vbo = gl.buffer(_QUAD.tobytes())
            self._vao = gl.simple_vertex_array(self._program, vbo, "in_vert")

        prog = self._program

        if self._band_history.shape[0] > 0:
            f_idx = max(0, min(ctx.time.frame, self._band_history.shape[0] - 1))
            bands = self._band_history[f_idx]
            shader_time = float(self._time_history[f_idx])
            punch = float(self._punch_history[f_idx])
            level = float(self._level_history[f_idx])
        else:
            ranges = _band_ranges(_N_BANDS)
            af = ctx.audio_bus_frame
            freq = np.asarray(af.spectrum, dtype="f4")
            raw = np.array([_mean_group(freq, start, end) for start, end in ranges], dtype="f4")
            bands = _shape_bands(raw, float(self.sensitivity))
            shader_time = ctx.time.t * float(self.speed)
            punch = 1.0 if (af.beat or af.onset) else 0.0
            level = float(af.amplitude)

        cr, cg, cb, _ = resolve_color(self.color, ctx.job.colors).rgba

        self._set_uniform(prog, "u_res", (self._bounds_w, self._bounds_h))
        self._set_uniform(prog, "u_origin", (self._bounds_x, self._bounds_y))
        self._set_uniform(prog, "u_canvas_h", self._canvas_h)
        self._set_uniform(prog, "u_time", shader_time)
        self._set_uniform(prog, "u_pan_y", (float(self.offset_y) - 0.5) * self._bounds_h)
        self._set_uniform(prog, "u_brightness", float(self.brightness))
        self._set_uniform(prog, "u_brightness_gain", float(self.brightness_reactivity))
        self._set_uniform(prog, "u_level", level)
        self._set_uniform(prog, "u_color", (cr, cg, cb))
        self._set_uniform(prog, "u_colorize", float(self.colorize))
        self._set_uniform(prog, "u_luma_alpha", float(self.luma_alpha))
        self._set_uniform(prog, "u_punch", punch * float(self.beat_punch))
        self._set_uniform(prog, "u_steps", int(self.quality))
        self._set_band_gains(prog, bands)

        bnd = ctx.bounds
        gl.scissor = (
            int(self._bounds_x),
            int(ctx.job.height - self._bounds_y - bnd.height),
            int(self._bounds_w),
            int(self._bounds_h),
        )

        assert self._vao is not None
        self._vao.render(moderngl.TRIANGLES)

        gl.scissor = None
