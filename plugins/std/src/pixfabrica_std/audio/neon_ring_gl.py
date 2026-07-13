from __future__ import annotations

from typing import Any, ClassVar, Literal

import moderngl
import numpy as np
from pydantic import Field, PrivateAttr, field_validator

from pixfabrica_core.audio.bus import N_SPECTRUM, AudioBusFrame
from pixfabrica_core.audio.mixin import AudioVisualMixin
from pixfabrica_core.clips import (
    ClipCategory,
    ClipGL,
    ClipPreset,
    ClipTag,
    PrepareContext,
    RenderContext,
)
from pixfabrica_core.graphics import Rect
from pixfabrica_core.theme.color import Color, ColorPalette, ColorToken, resolve_color

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
uniform float u_t;

uniform float u_offset_x;
uniform float u_offset_y;
uniform float u_width;

uniform float u_bar_count_f;
uniform float u_bar_heights[90];
uniform float u_bass;
uniform float u_has_bus;
uniform float u_idle_animate;
uniform float u_min_spike;

uniform float u_has_bg;
uniform vec3  u_color_background;
uniform float u_opacity;

uniform vec3  u_palette_c0;
uniform vec3  u_palette_c1;
uniform vec3  u_palette_c2;
uniform vec3  u_palette_c3;

out vec4 frag_color;

#define PI 3.14159265

// Ring geometry in normalized UV space.
#define RING_R     0.30
#define BAR_BASE   0.365
#define BAR_MAX    0.22
#define DASH_SIZE  0.016
// Spike tips + sweep halo; width=1.0 maps this extent to min(bounds) / 2.
#define OUTER_EXTENT 0.62

// Radial spike angular mask (smooth edges within each sector).
#define ANG_IN0  0.18
#define ANG_IN1  0.34
#define ANG_OUT0 0.82
#define ANG_OUT1 0.66

// Spike shaping and root glow.
#define SPIKE_GAIN      1.4
#define SPIKE_BRIGHT    1.6
#define SPIKE_ROOT_EXP  30.0
#define SPIKE_ROOT_GAIN 0.15
#define TIP_FADE        0.55

// Main neon ring falloff.
#define RING_CORE_EXP  110.0
#define RING_HALO_EXP  14.0
#define RING_CORE_GAIN 1.6
#define RING_HALO_GAIN 0.30
#define BASS_RADIUS_GAIN 0.015

// Decorative sweeping arc (not timeline progress).
#define SWEEP_SPEED        0.06
#define SWEEP_END_IN       0.06
#define SWEEP_END_OUT      0.32
#define SWEEP_END_FADE     0.24
#define SWEEP_RADIUS_OFF   0.028
#define SWEEP_CORE_EXP     80.0
#define SWEEP_HALO_EXP     16.0
#define SWEEP_CORE_GAIN    2.2
#define SWEEP_HALO_GAIN    0.35
#define SWEEP_WHITE_MIX    0.35

// Inner tick ring inside the main ring.
#define TICK_RADIUS_INSET 0.045
#define TICK_EXP          160.0
#define TICK_GAIN         0.50

// Palette drift around the ring (fraction of circle per unit u_t).
#define PALETTE_DRIFT 0.02
#define PALETTE_PHASE 0.15

// Idle spike fallback when no bus is wired (matches Shadertoy motion).
#define IDLE_FREQ_A 3.0
#define IDLE_FREQ_B 1.3
#define IDLE_FX_A   25.0
#define IDLE_FX_B   7.0
#define IDLE_GAIN   0.8

vec3 palette(float t) {
    t = fract(t);
    if (t < 0.3333) return mix(u_palette_c0, u_palette_c1, t * 3.0);
    if (t < 0.6666) return mix(u_palette_c1, u_palette_c2, (t - 0.3333) * 3.0);
    return mix(u_palette_c2, u_palette_c3, (t - 0.6666) * 3.0);
}

vec4 extractAlpha(vec3 colorIn) {
    float maxValue = min(max(max(colorIn.r, colorIn.g), colorIn.b), 1.0);
    if (maxValue > 1e-5)
        return vec4(colorIn * (1.0 / maxValue), maxValue);
    return vec4(0.0);
}

float mirroredFx(float sector) {
    return abs(fract(sector / u_bar_count_f + 0.25) * 2.0 - 1.0);
}

float idleAudio(float fx) {
    float a = sin(u_t * IDLE_FREQ_A + fx * IDLE_FX_A) * 0.5 + 0.5;
    a *= sin(u_t * IDLE_FREQ_B + fx * IDLE_FX_B) * 0.5 + 0.5;
    return a * IDLE_GAIN;
}

float sectorAudio(float sector) {
    if (u_has_bus > 0.5) {
        int idx = int(clamp(sector, 0.0, u_bar_count_f - 1.0));
        return u_bar_heights[idx];
    }
    if (u_idle_animate > 0.5)
        return idleAudio(mirroredFx(sector));
    return u_min_spike;
}

void main() {
    float px = gl_FragCoord.x - u_origin.x;
    float py = (u_canvas_h - gl_FragCoord.y) - u_origin.y;

    if (px < 0.0 || px >= u_res.x || py < 0.0 || py >= u_res.y) discard;

    float min_dim = min(u_res.x, u_res.y);
    float layout_radius = u_width * min_dim * 0.5;
    float norm = max(layout_radius / OUTER_EXTENT, 1.0);

    float cx = u_res.x * u_offset_x;
    float cy = u_res.y * u_offset_y;

    vec2 uv = (vec2(px, py) - vec2(cx, cy)) / norm;
    uv.y = -uv.y;

    float r   = length(uv);
    float ang = atan(uv.y, uv.x);
    float a01 = ang / (2.0 * PI) + 0.5;

    float hueT = fract(a01 + PALETTE_PHASE + u_t * PALETTE_DRIFT);
    vec3  hue  = palette(hueT);

    float bass = u_has_bus > 0.5 ? u_bass : (u_idle_animate > 0.5 ? idleAudio(0.05) : 0.0);
    float r0 = RING_R + bass * bass * BASS_RADIUS_GAIN;

    vec3 col = u_has_bg > 0.5 ? u_color_background : vec3(0.0);

    float sector = floor(a01 * u_bar_count_f);
    float audio = sectorAudio(sector);
    audio = audio * audio * SPIKE_GAIN;

    float barLen = u_min_spike + audio * BAR_MAX;

    float f = fract(a01 * u_bar_count_f);
    float angMask = smoothstep(ANG_IN0, ANG_IN1, f) * smoothstep(ANG_OUT0, ANG_OUT1, f);

    float inBar = step(BAR_BASE, r) * step(r, BAR_BASE + barLen);

    float d = fract((r - BAR_BASE) / DASH_SIZE);
    float dashMask = smoothstep(0.15, 0.35, d) * smoothstep(0.95, 0.75, d);

    float tipFade = 1.0 - smoothstep(BAR_BASE, BAR_BASE + barLen, r) * TIP_FADE;

    col += hue * angMask * inBar * dashMask * tipFade * SPIKE_BRIGHT;

    col += hue * angMask * exp(-max(r - BAR_BASE, 0.0) * SPIKE_ROOT_EXP)
               * step(BAR_BASE, r) * SPIKE_ROOT_GAIN;

    float d0 = abs(r - r0);
    col += hue * (exp(-d0 * RING_CORE_EXP) * RING_CORE_GAIN
                + exp(-d0 * RING_HALO_EXP)  * RING_HALO_GAIN);

    float arcA = fract(a01 - u_t * SWEEP_SPEED);
    float arcMask = smoothstep(0.00, SWEEP_END_IN, arcA)
                  * smoothstep(SWEEP_END_OUT, SWEEP_END_FADE, arcA);
    float d1 = abs(r - (r0 + SWEEP_RADIUS_OFF));
    vec3 arcCol = mix(hue, vec3(1.0), SWEEP_WHITE_MIX);
    col += arcCol * arcMask * (exp(-d1 * SWEEP_CORE_EXP) * SWEEP_CORE_GAIN
                             + exp(-d1 * SWEEP_HALO_EXP) * SWEEP_HALO_GAIN);

    float tick = smoothstep(0.25, 0.4, abs(fract(a01 * u_bar_count_f) - 0.5));
    float d2 = abs(r - (r0 - TICK_RADIUS_INSET));
    col += hue * (1.0 - tick) * exp(-d2 * TICK_EXP) * TICK_GAIN;

    col = sqrt(max(col, 0.0));

    if (u_has_bg > 0.5) {
        frag_color = vec4(col * u_opacity, u_opacity);
    } else {
        vec4 extracted = extractAlpha(col);
        float out_a = extracted.a * u_opacity;
        frag_color = vec4(extracted.rgb * out_a, out_a);
    }
}
"""

_QUAD = np.array(
    [-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0],
    dtype="f4",
)

_MAX_BARS = 90
_MIN_BARS = 48
_PEAK_PCT = 90.0
_HEADROOM = 0.88
_SAT_GAIN = 0.48
_SPECTRUM_FX_SCALE = 0.7
_MIN_SPIKE_FRAC = 0.025 / 0.22  # matches shader BAR_MAX default spike floor

# Built-in neon gradient when color_primary / color_secondary are unset.
_DEFAULT_PALETTE = (
    (0.10, 0.95, 1.00),
    (0.25, 0.40, 1.00),
    (0.65, 0.25, 1.00),
    (1.00, 0.30, 0.85),
)

IdleMode = Literal["animate", "static"]


def _lerp3(
    a: tuple[float, float, float], b: tuple[float, float, float], t: float
) -> tuple[float, float, float]:
    return (
        a[0] + (b[0] - a[0]) * t,
        a[1] + (b[1] - a[1]) * t,
        a[2] + (b[2] - a[2]) * t,
    )


def resolve_palette_colors(
    primary: ColorToken | Color | None,
    secondary: ColorToken | Color | None,
    palette: ColorPalette,
) -> tuple[tuple[float, float, float], ...]:
    """Return four RGB stops for the ring gradient."""
    if primary is None and secondary is None:
        return _DEFAULT_PALETTE

    p = resolve_color(primary if primary is not None else ColorToken.PRIMARY, palette)
    s = resolve_color(
        secondary
        if secondary is not None
        else (primary if primary is not None else ColorToken.ACCENT),
        palette,
    )
    pr, pg, pb, _ = p.rgba
    sr, sg, sb, _ = s.rgba
    start = (float(pr), float(pg), float(pb))
    end = (float(sr), float(sg), float(sb))
    return (
        start,
        _lerp3(start, end, 1.0 / 3.0),
        _lerp3(start, end, 2.0 / 3.0),
        end,
    )


def _sector_fx(sector: int, bar_count: int) -> float:
    return abs((sector / float(bar_count) + 0.25) % 1.0 * 2.0 - 1.0)


def _spectrum_bin_for_fx(fx: float) -> int:
    return int(round(min(max(fx * _SPECTRUM_FX_SCALE, 0.0), 1.0) * (N_SPECTRUM - 1)))


def _shape_row(row: np.ndarray, sensitivity: float) -> np.ndarray:
    peak = float(np.percentile(row, _PEAK_PCT))
    if peak <= 1e-8:
        return np.zeros_like(row)
    normalized = row / peak
    shaped = np.tanh(normalized * float(sensitivity) * _SAT_GAIN)
    return (shaped * _HEADROOM).astype(np.float32)


def _normalize_bass(frames: list[AudioBusFrame], n_bus: int) -> np.ndarray:
    if n_bus <= 0:
        return np.zeros(0, dtype=np.float32)
    raw = np.asarray([float(frames[f].bass) for f in range(n_bus)], dtype=np.float32)
    lo, hi = np.percentile(raw, (5.0, 95.0))
    span = max(float(hi - lo), 1e-6)
    return np.clip((raw - lo) / span, 0.0, 1.0).astype(np.float32)


class NeonRingGL(AudioVisualMixin, ClipGL):
    """Neon ring spectrum — radial LED spikes, orbiting highlight arc, and bass-reactive glow."""

    clip_type: ClassVar[str] = "std-neon-ring-gl"
    clip_category: ClassVar[ClipCategory] = ClipCategory.AUDIO
    clip_tags: ClassVar[list[str]] = [ClipTag.AUDIO_REACTIVE, ClipTag.ANIMATED, ClipTag.GL]
    clip_presets: ClassVar[list[ClipPreset]] = [
        ClipPreset(id="default", label="Overlay", values={}),
        ClipPreset(
            id="dark_stage",
            label="Dark Stage",
            values={"color_background": ColorToken.BACKGROUND.value},
        ),
    ]

    bar_count: int = Field(
        default=90,
        ge=_MIN_BARS,
        le=_MAX_BARS,
        multiple_of=1,
        description="Number of radial LED spikes around the ring (48–90)",
    )
    color_primary: ColorToken | Color | None = Field(
        default=None,
        description="Optional gradient start; unset keeps the built-in neon palette",
        json_schema_extra={"widget": "color"},
    )
    color_secondary: ColorToken | Color | None = Field(
        default=None,
        description="Optional gradient end; unset keeps the built-in neon palette",
        json_schema_extra={"widget": "color"},
    )
    color_background: ColorToken | Color | None = Field(
        default=None,
        description="Panel fill color; unset = transparent background with luma alpha",
        json_schema_extra={"widget": "color"},
    )
    idle_mode: IdleMode = Field(
        default="animate",
        description="Spike motion when no bus is wired: animate (demo fallback) or static minimum",
    )
    offset_x: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Horizontal center (0=left, 0.5=center, 1=right)",
    )
    offset_y: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Vertical center (0=top, 0.5=center, 1=bottom)",
    )
    width: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Overall diameter as a fraction of min(bounds width, height), including outer spikes",
    )
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    speed: float = Field(
        default=1.0,
        ge=0.1,
        le=3.0,
        multiple_of=0.1,
        description="Animation speed for palette drift and decorative sweep arc",
    )
    sensitivity: float = Field(
        default=2.5,
        ge=0.1,
        le=8.0,
        multiple_of=0.1,
        description="Audio response gain on spike heights after job-wide normalization",
    )
    smoothing: float = Field(
        default=0.45,
        ge=0.0,
        le=0.9,
        multiple_of=0.05,
        description="Temporal EMA smoothing on spectrum (0 = raw, 0.9 = sluggish)",
    )

    _canvas_h: float = PrivateAttr(default=0.0)
    _bounds_x: float = PrivateAttr(default=0.0)
    _bounds_y: float = PrivateAttr(default=0.0)
    _bounds_w: float = PrivateAttr(default=0.0)
    _bounds_h: float = PrivateAttr(default=0.0)
    _program: moderngl.Program | None = PrivateAttr(default=None)
    _vao: moderngl.VertexArray | None = PrivateAttr(default=None)
    _bar_history: np.ndarray = PrivateAttr(
        default_factory=lambda: np.zeros((0, _MAX_BARS), dtype="f4")
    )
    _bass_history: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype="f4"))
    _has_bus_timeline: bool = PrivateAttr(default=False)

    @field_validator("bar_count", mode="before")
    @classmethod
    def _clamp_bar_count(cls, value: Any) -> int:
        n = int(value)
        return max(_MIN_BARS, min(n, _MAX_BARS))

    async def prepare(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        b = bounds or Rect(0, 0, ctx.job.width, ctx.job.height)
        self._canvas_h = float(ctx.job.height)
        self._bounds_x = float(b.x)
        self._bounds_y = float(b.y)
        self._bounds_w = float(b.width)
        self._bounds_h = float(b.height)
        self._bar_history, self._bass_history, self._has_bus_timeline = self._precompute_audio(ctx)

    def _precompute_audio(self, ctx: PrepareContext) -> tuple[np.ndarray, np.ndarray, bool]:
        total = max(ctx.job.total_frames, 0)
        history = np.zeros((total, _MAX_BARS), dtype="f4")
        bass_history = np.zeros(total, dtype="f4")
        if total == 0:
            return history, bass_history, False

        frames: list[AudioBusFrame] | None = self.bus_timeline(ctx)
        if not frames:
            return history, bass_history, False

        n = self.bar_count
        sector_bins = np.array(
            [_spectrum_bin_for_fx(_sector_fx(i, n)) for i in range(n)],
            dtype=np.int64,
        )

        s = float(self.smoothing)
        one_minus_s = 1.0 - s
        sens = float(self.sensitivity)
        n_bus = min(total, len(frames))
        bass_norm = _normalize_bass(frames, n_bus)
        prev = np.zeros(n, dtype="f4")
        bass_state = 0.0

        for f in range(total):
            if f < n_bus:
                freq = np.asarray(frames[f].spectrum, dtype="f4")
                raw = np.clip(freq[sector_bins], 0.0, 1.0)
                prev = prev * s + raw * one_minus_s
                bass_state = bass_state * s + float(bass_norm[f]) * one_minus_s
            else:
                prev = prev * s
                bass_state = bass_state * s
            history[f, :n] = _shape_row(prev, sens)
            bass_history[f] = float(bass_state)

        return history, bass_history, True

    def _set_uniform(self, prog: moderngl.Program, name: str, value: Any) -> None:
        if name in prog:
            member = prog[name]
            if isinstance(member, moderngl.Uniform):
                member.value = value

    def _set_bar_heights(self, prog: moderngl.Program, bar_heights: np.ndarray, n: int) -> None:
        if "u_bar_heights[0]" in prog:
            for i in range(n):
                self._set_uniform(prog, f"u_bar_heights[{i}]", float(bar_heights[i]))
        elif "u_bar_heights" in prog:
            member = prog["u_bar_heights"]
            if isinstance(member, moderngl.Uniform):
                padded = tuple(float(bar_heights[i]) if i < n else 0.0 for i in range(_MAX_BARS))
                member.value = padded  # type: ignore[assignment]

    def _bar_heights_for_frame(self, ctx: RenderContext) -> tuple[np.ndarray, float, bool]:
        n = self.bar_count
        heights = np.zeros(_MAX_BARS, dtype="f4")

        if self._has_bus_timeline and self._bar_history.shape[0] > 0:
            f_idx = max(0, min(ctx.time.frame, self._bar_history.shape[0] - 1))
            heights[:n] = self._bar_history[f_idx, :n]
            bass = float(self._bass_history[f_idx]) if self._bass_history.size else 0.0
            return heights, bass, True

        if self.bus_active_for_draw(ctx):
            sector_bins = [_spectrum_bin_for_fx(_sector_fx(i, n)) for i in range(n)]
            freq = np.asarray(ctx.audio_bus_frame.spectrum, dtype="f4")
            raw = np.clip(freq[sector_bins], 0.0, 1.0)
            heights[:n] = _shape_row(raw, float(self.sensitivity))
            bass = min(1.0, max(0.0, float(ctx.audio_bus_frame.bass) * float(self.sensitivity)))
            return heights, bass, True

        return heights, 0.0, False

    def draw(self, ctx: RenderContext) -> None:
        if self.width <= 0.0:
            return

        gl: moderngl.Context = ctx.canvas

        if self._program is None:
            self._program = gl.program(vertex_shader=_VERT, fragment_shader=_FRAG)
            vbo = gl.buffer(_QUAD.tobytes())
            self._vao = gl.simple_vertex_array(self._program, vbo, "in_vert")

        prog = self._program
        n = self.bar_count
        bar_heights, bass, has_bus = self._bar_heights_for_frame(ctx)
        palette = resolve_palette_colors(self.color_primary, self.color_secondary, ctx.job.colors)

        self._set_uniform(prog, "u_res", (self._bounds_w, self._bounds_h))
        self._set_uniform(prog, "u_origin", (self._bounds_x, self._bounds_y))
        self._set_uniform(prog, "u_canvas_h", self._canvas_h)
        self._set_uniform(prog, "u_t", float(ctx.time.t) * float(self.speed))
        self._set_uniform(prog, "u_offset_x", self.offset_x)
        self._set_uniform(prog, "u_offset_y", self.offset_y)
        self._set_uniform(prog, "u_width", self.width)
        self._set_uniform(prog, "u_bar_count_f", float(n))
        self._set_bar_heights(prog, bar_heights, n)
        self._set_uniform(prog, "u_bass", bass)
        self._set_uniform(prog, "u_has_bus", 1.0 if has_bus else 0.0)
        self._set_uniform(prog, "u_idle_animate", 1.0 if self.idle_mode == "animate" else 0.0)
        self._set_uniform(prog, "u_min_spike", _MIN_SPIKE_FRAC)
        self._set_uniform(prog, "u_opacity", self.opacity)
        self._set_uniform(prog, "u_palette_c0", palette[0])
        self._set_uniform(prog, "u_palette_c1", palette[1])
        self._set_uniform(prog, "u_palette_c2", palette[2])
        self._set_uniform(prog, "u_palette_c3", palette[3])

        if self.color_background is not None:
            br, bg, bb, _ = resolve_color(self.color_background, ctx.job.colors).rgba
            self._set_uniform(prog, "u_has_bg", 1.0)
            self._set_uniform(prog, "u_color_background", (br, bg, bb))
        else:
            self._set_uniform(prog, "u_has_bg", 0.0)
            self._set_uniform(prog, "u_color_background", (0.0, 0.0, 0.0))

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
