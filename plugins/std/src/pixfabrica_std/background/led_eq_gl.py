from __future__ import annotations

from typing import Any, ClassVar

import moderngl
import numpy as np
from pydantic import Field, PrivateAttr

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
from pixfabrica_core.theme.color import Color, ColorToken, color_field, resolve_color

# ---------------------------------------------------------------------------
# Tunable defaults — adjust here; passed to the shader as uniforms each frame.
# ---------------------------------------------------------------------------
_MAX_BARS = 64
_MAX_LEDS = 32

# EQ layout (normalized UV space, y-up)
_EQ_WIDTH = 1.6
_EQ_BASE_Y = -0.2
_EQ_MAX_HEIGHT = 0.6

# Portrait — uv.x spans ±aspect/2; EQ width must fit inside that span.
_LANDSCAPE_REF_ASPECT = 16.0 / 9.0
_PORTRAIT_EQ_WIDTH_MARGIN = 0.92
_PORTRAIT_MIN_BARS = 16
_PORTRAIT_BAR_ASPECT_POWER = 1.0

# Motion
_GRID_SCROLL_SPEED = 2.0
_DEMO_PULSE_SPEED = 3.0
_DEMO_BASS_SPEED = 2.0

# Layer appearance
_GRID_COLOR = (0.05, 0.2, 0.4)
_GRID_BASS_GAIN = 0.8
_REFLECTION_BASE_OPACITY = 0.25
_BLOOM_STRENGTH = 0.5
_GHOST_LED_ALPHA = 0.28
_GHOST_CELL_TINT = 0.22
_GHOST_CELL_BASE = (0.09, 0.09, 0.11)
_PEAK_GLOW_BOOST = 1.5
_VIGNETTE_AMOUNT = 0.4
_SPARK_COUNT = 15
_SPARK_BASE_GAIN = 0.0015

# Audio shaping
_AUDIO_SHAPE_POWER = 1.2
_DEMO_PULSE_AMP = 0.4
_DEMO_BASS_AMP = 0.3

# Classic synthwave preset colors (cyan → magenta)
_CLASSIC_COLOR_LOW_HEX = "#00CCFF"
_CLASSIC_COLOR_HIGH_HEX = "#FF00CC"

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

uniform float u_eff_t;
uniform float u_bar_count_f;
uniform float u_led_count_f;
uniform float u_bar_heights[64];
uniform float u_bass;
uniform float u_demo_mode;

uniform vec3  u_color_low;
uniform vec3  u_color_high;

uniform float u_grid_intensity;
uniform float u_reflection_strength;
uniform float u_spark_intensity;
uniform float u_vignette;

uniform float u_eq_width;
uniform float u_eq_base_y;
uniform float u_eq_max_height;
uniform float u_grid_scroll_speed;
uniform float u_demo_pulse_speed;
uniform float u_demo_bass_speed;
uniform float u_reflection_base;
uniform float u_bloom_strength;
uniform float u_ghost_led_alpha;
uniform float u_peak_glow_boost;
uniform float u_audio_shape_power;
uniform vec3  u_grid_color;
uniform float u_vignette_amount;
uniform float u_spark_count_f;
uniform float u_spark_base_gain;
uniform float u_grid_bass_gain;
uniform float u_demo_pulse_amp;
uniform float u_demo_bass_amp;
uniform vec3  u_ghost_cell_base;
uniform float u_ghost_cell_tint;

out vec4 frag_color;

float sdBox(vec2 p, vec2 b, float r) {
    vec2 d = abs(p) - b + vec2(r);
    return length(max(d, 0.0)) + min(max(d.x, d.y), 0.0) - r;
}

float barAudio(float barIndex, float freqX) {
    int idx = int(barIndex);
    if (idx < 0 || idx >= 64) return 0.0;
    float audio = u_bar_heights[idx];
    if (u_demo_mode > 0.5 && audio < 0.01) {
        audio = (sin(u_eff_t * u_demo_pulse_speed + freqX * 10.0) * 0.5 + 0.5) * u_demo_pulse_amp;
    }
    return pow(max(audio, 0.0), u_audio_shape_power);
}

void main() {
    float px = gl_FragCoord.x - u_origin.x;
    float py = (u_canvas_h - gl_FragCoord.y) - u_origin.y;

    vec2 uv = (vec2(px, py) - u_res * 0.5) / u_res.y;
    // Pixfabrica py is y-down; Shadertoy fragCoord is y-up — flip to match original.
    uv.y = -uv.y;

    float eqWidth = u_eq_width;
    float xPos = uv.x / eqWidth + 0.5;

    vec3 col = vec3(0.0);

    float bass = u_bass;
    if (u_demo_mode > 0.5 && bass < 0.01) {
        bass = (sin(u_eff_t * u_demo_bass_speed) * 0.5 + 0.5) * u_demo_bass_amp;
    }

    // Perspective bass grid
    vec2 gridUv = uv;
    gridUv.y += 0.2;
    if (gridUv.y > 0.0 && u_grid_intensity > 0.0) {
        float z = 0.1 / gridUv.y;
        float x = gridUv.x * z;
        z -= u_eff_t * u_grid_scroll_speed;

        float gridLines = smoothstep(0.05, 0.0, abs(fract(x * 5.0) - 0.5))
                        + smoothstep(0.05, 0.0, abs(fract(z * 5.0) - 0.5));

        float gridFade = exp(-gridUv.y * 20.0);
        col += u_grid_color * gridLines * gridFade * bass * u_grid_bass_gain * u_grid_intensity;
    }

    // LED equalizer bars
    if (xPos >= 0.0 && xPos <= 1.0) {
        float barIndex = floor(xPos * u_bar_count_f);
        float freqX = barIndex / u_bar_count_f;
        float audio = barAudio(barIndex, freqX);

        float localX = fract(xPos * u_bar_count_f);
        float baseY = u_eq_base_y;
        float barHeight = u_eq_max_height;

        float ledRaw = (uv.y - baseY) / barHeight * u_led_count_f;
        float ledIndex = floor(ledRaw);
        float ledDistY = fract(ledRaw);

        if (ledIndex >= 0.0 && ledIndex < u_led_count_f) {
            float isLit = step(ledIndex, audio * u_led_count_f);

            vec3 colorA = mix(u_color_low, u_color_high, freqX);
            vec3 ledColor = mix(colorA, vec3(1.0), ledIndex / u_led_count_f);

            vec2 blockUv = vec2(localX, ledDistY) - 0.5;
            // Keep LED blocks square on screen (bar slots are wider than LED rows in uv space).
            float cellAspect = (eqWidth / u_bar_count_f) / (barHeight / u_led_count_f);
            blockUv.x *= cellAspect;
            float blockDist = sdBox(blockUv, vec2(0.35, 0.35), 0.1);
            float blockMask = smoothstep(0.05, 0.0, blockDist);

            col += ledColor * blockMask * isLit;
            col += ledColor * exp(-blockDist * 5.0) * u_bloom_strength * isLit;
            vec3 ghostColor = mix(u_ghost_cell_base, ledColor, u_ghost_cell_tint);
            col += ghostColor * blockMask * (1.0 - isLit) * u_ghost_led_alpha;

            float isPeak = step(abs(ledIndex - floor(audio * u_led_count_f)), 0.1);
            col += ledColor * blockMask * isPeak * u_peak_glow_boost;
        }

        // Floor reflection
        if (u_reflection_strength > 0.0) {
            float reflectRaw = (baseY - uv.y) / barHeight * u_led_count_f;
            float refLedIndex = floor(reflectRaw);
            float refLedDistY = fract(reflectRaw);

            if (refLedIndex >= 0.0 && refLedIndex < u_led_count_f && uv.y < baseY) {
                float isLit = step(refLedIndex, audio * u_led_count_f);
                vec3 colorA = mix(u_color_low, u_color_high, freqX);
                vec3 ledColor = mix(colorA, vec3(1.0), refLedIndex / u_led_count_f);

                vec2 blockUv = vec2(localX, refLedDistY) - 0.5;
                float cellAspect = (eqWidth / u_bar_count_f) / (barHeight / u_led_count_f);
                blockUv.x *= cellAspect;
                float blockDist = sdBox(blockUv, vec2(0.35, 0.35), 0.1);
                float blockMask = smoothstep(0.05, 0.0, blockDist);

                float refFade = 1.0 - (refLedIndex / (audio * u_led_count_f + 1.0));
                refFade *= smoothstep(0.0, -0.2, uv.y - baseY);

                col += ledColor * blockMask * isLit * refFade
                      * u_reflection_base * u_reflection_strength;
            }
        }
    }

    // Audio-reactive sparks
    if (u_spark_intensity > 0.0) {
        int sparkCount = int(u_spark_count_f);
        for (int i = 0; i < 15; i++) {
            if (i >= sparkCount) break;
            float fi = float(i);
            float speed = 0.2 + fract(sin(fi * 123.4) * 10.0);
            float startX = fract(sin(fi * 321.4) * 45.6);
            float pySpark = fract(u_eff_t * speed + fi);

            float barIdx = floor(startX * u_bar_count_f);
            float pAudio = barAudio(barIdx, startX);

            vec2 pUv = vec2((startX - 0.5) * eqWidth, u_eq_base_y + pySpark * pAudio * 1.5);
            float pDist = length(uv - pUv);

            vec3 pColor = mix(u_color_low, u_color_high, startX);
            float pIntensity = smoothstep(0.3, 0.8, pAudio);
            col += pColor * (u_spark_base_gain / max(pDist, 1e-4)) * pIntensity
                  * (1.0 - pySpark) * u_spark_intensity;
        }
    }

    if (u_vignette > 0.0) {
        col *= 1.0 - dot(uv, uv) * u_vignette_amount * u_vignette;
    }

    frag_color = vec4(pow(col, vec3(1.0 / 2.2)), 1.0);
}
"""

_QUAD = np.array(
    [-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0],
    dtype="f4",
)


def _resample_bins(spectrum: np.ndarray, n: int) -> np.ndarray:
    idxs = np.linspace(0, N_SPECTRUM - 1, n).astype(np.int64)
    return np.clip(spectrum[idxs], 0.0, 1.0)


def _resample_bars(heights: np.ndarray, n_src: int, n_dst: int) -> np.ndarray:
    """Downsample precomputed bar columns for portrait layout."""
    if n_dst >= n_src:
        out = np.zeros(_MAX_BARS, dtype="f4")
        out[:n_src] = heights[:n_src]
        return out
    idxs = np.linspace(0, n_src - 1, n_dst).astype(np.int64)
    out = np.zeros(_MAX_BARS, dtype="f4")
    out[:n_dst] = heights[idxs]
    return out


def _adaptive_layout(
    width: float,
    height: float,
    bar_count: int,
    led_count: int,
) -> tuple[float, float, float, int, int]:
    """Shrink EQ width and bar count in portrait so the grid fits horizontal space."""
    aspect = width / max(height, 1.0)
    eq_width = _EQ_WIDTH
    eq_base_y = _EQ_BASE_Y
    eq_max_height = _EQ_MAX_HEIGHT
    eff_bars = bar_count
    eff_leds = led_count

    if aspect < 1.0:
        eq_width = min(_EQ_WIDTH, aspect * _PORTRAIT_EQ_WIDTH_MARGIN)
        scale = (aspect / _LANDSCAPE_REF_ASPECT) ** _PORTRAIT_BAR_ASPECT_POWER
        eff_bars = max(_PORTRAIT_MIN_BARS, min(bar_count, int(round(bar_count * scale))))

    return eq_width, eq_base_y, eq_max_height, eff_bars, eff_leds


def _normalize_bass(frames: list[AudioBusFrame], n_bus: int) -> np.ndarray:
    if n_bus <= 0:
        return np.zeros(0, dtype=np.float32)
    raw = np.asarray([float(frames[f].bass) for f in range(n_bus)], dtype=np.float32)
    lo, hi = np.percentile(raw, (5.0, 95.0))
    span = max(float(hi - lo), 1e-6)
    return np.clip((raw - lo) / span, 0.0, 1.0).astype(np.float32)


class LedEqGL(AudioVisualMixin, ClipGL):
    """Full-bleed cinematic LED equalizer — perspective bass grid, segmented bars,
    floor reflection, and audio-reactive sparks driven by a named audio bus."""

    clip_type: ClassVar[str] = "std-led-eq-gl"
    clip_category: ClassVar[ClipCategory] = ClipCategory.BACKGROUND
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED, ClipTag.GL, ClipTag.AUDIO_REACTIVE]
    clip_presets: ClassVar[list[ClipPreset]] = [
        ClipPreset(id="default", label="Default", values={}),
        ClipPreset(
            id="classic",
            label="Classic",
            values={
                "color_low": _CLASSIC_COLOR_LOW_HEX,
                "color_high": _CLASSIC_COLOR_HIGH_HEX,
            },
        ),
        ClipPreset(
            id="minimal",
            label="Minimal",
            values={
                "grid_intensity": 0.4,
                "spark_intensity": 0.3,
                "vignette": 0.6,
                "reflection_strength": 0.5,
            },
        ),
    ]

    bar_count: int = Field(
        default=40,
        ge=16,
        le=_MAX_BARS,
        multiple_of=1,
        description="Number of vertical EQ bar columns",
    )
    led_count: int = Field(
        default=20,
        ge=8,
        le=_MAX_LEDS,
        multiple_of=1,
        description="LED segments per bar column",
    )
    color_low: ColorToken | Color = color_field(
        ColorToken.SECONDARY, default=Color(_CLASSIC_COLOR_LOW_HEX)
    )
    color_high: ColorToken | Color = color_field(
        ColorToken.PRIMARY, default=Color(_CLASSIC_COLOR_HIGH_HEX)
    )
    sensitivity: float = Field(
        default=2.5,
        ge=0.1,
        le=8.0,
        multiple_of=0.05,
        description="Audio response gain on bar heights after job-wide normalization",
    )
    smoothing: float = Field(
        default=0.35,
        ge=0.0,
        le=0.95,
        multiple_of=0.05,
        description="Temporal EMA on bar heights (0 = raw, 0.95 = sluggish)",
    )
    speed: float = Field(
        default=1.0,
        ge=0.25,
        le=3.0,
        multiple_of=0.05,
        description="Global animation speed multiplier",
    )
    grid_intensity: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.05,
        description="Perspective bass grid brightness (0 = off)",
    )
    reflection_strength: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.05,
        description="Floor reflection multiplier (0 = off)",
    )
    spark_intensity: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.05,
        description="Rising spark particles (0 = off)",
    )
    vignette: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.05,
        description="Edge darkening (0 = off)",
    )

    _canvas_h: float = PrivateAttr(default=0.0)
    _bounds_x: float = PrivateAttr(default=0.0)
    _bounds_y: float = PrivateAttr(default=0.0)
    _bounds_w: float = PrivateAttr(default=0.0)
    _bounds_h: float = PrivateAttr(default=0.0)

    _bar_history: np.ndarray = PrivateAttr(
        default_factory=lambda: np.zeros((0, _MAX_BARS), dtype="f4")
    )
    _bass_history: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype="f4"))
    _program: moderngl.Program | None = PrivateAttr(default=None)
    _vao: moderngl.VertexArray | None = PrivateAttr(default=None)

    async def prepare(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        b = bounds or Rect(0, 0, ctx.job.width, ctx.job.height)
        self._canvas_h = float(ctx.job.height)
        self._bounds_x = float(b.x)
        self._bounds_y = float(b.y)
        self._bounds_w = float(b.width)
        self._bounds_h = float(b.height)
        self._bar_history, self._bass_history = self._precompute_audio_history(ctx)

    def _precompute_audio_history(self, ctx: PrepareContext) -> tuple[np.ndarray, np.ndarray]:
        total = max(ctx.job.total_frames, 0)
        bar_history = np.zeros((total, _MAX_BARS), dtype="f4")
        bass_history = np.zeros(total, dtype="f4")
        if total == 0:
            return bar_history, bass_history

        frames: list[AudioBusFrame] | None = self.bus_timeline(ctx)
        if not frames:
            return bar_history, bass_history

        n = self.bar_count
        n_bus = min(total, len(frames))
        s = float(self.smoothing)
        one_minus_s = 1.0 - s
        sens = float(self.sensitivity)
        bass_norm = _normalize_bass(frames, n_bus)

        prev = np.zeros(n, dtype="f4")
        bass_prev = 0.0
        for f in range(total):
            if f >= n_bus:
                prev = prev * s
                bass_prev = bass_prev * s
            else:
                spec = np.asarray(frames[f].spectrum, dtype="f4")
                raw = _resample_bins(spec, n) * sens
                prev = prev * s + np.clip(raw, 0.0, 1.0) * one_minus_s
                bass_prev = bass_prev * s + float(bass_norm[f]) * one_minus_s
            bar_history[f, :n] = np.clip(prev, 0.0, 1.0)
            bass_history[f] = np.clip(bass_prev, 0.0, 1.0)

        return bar_history, bass_history

    def _runtime_bar_heights(self, ctx: RenderContext, n: int) -> np.ndarray:
        af = ctx.audio_bus_frame
        spec = np.asarray(af.spectrum, dtype="f4")
        return np.clip(_resample_bins(spec, n) * float(self.sensitivity), 0.0, 1.0)

    def _set_uniform(self, prog: moderngl.Program, name: str, value: Any) -> None:
        if name not in prog:
            return
        member = prog[name]
        if isinstance(member, moderngl.Uniform):
            member.value = value

    def _set_bar_heights(self, prog: moderngl.Program, heights: np.ndarray, n: int) -> None:
        padded = np.zeros(_MAX_BARS, dtype="f4")
        padded[:n] = heights[:n]
        if "u_bar_heights[0]" in prog:
            for i in range(_MAX_BARS):
                self._set_uniform(prog, f"u_bar_heights[{i}]", float(padded[i]))
        elif "u_bar_heights" in prog:
            member = prog["u_bar_heights"]
            if isinstance(member, moderngl.Uniform):
                member.value = tuple(padded.tolist())

    def _set_layout_constants(self, prog: moderngl.Program) -> None:
        self._set_uniform(prog, "u_grid_scroll_speed", _GRID_SCROLL_SPEED)
        self._set_uniform(prog, "u_demo_pulse_speed", _DEMO_PULSE_SPEED)
        self._set_uniform(prog, "u_demo_bass_speed", _DEMO_BASS_SPEED)
        self._set_uniform(prog, "u_reflection_base", _REFLECTION_BASE_OPACITY)
        self._set_uniform(prog, "u_bloom_strength", _BLOOM_STRENGTH)
        self._set_uniform(prog, "u_ghost_led_alpha", _GHOST_LED_ALPHA)
        self._set_uniform(prog, "u_ghost_cell_base", _GHOST_CELL_BASE)
        self._set_uniform(prog, "u_ghost_cell_tint", _GHOST_CELL_TINT)
        self._set_uniform(prog, "u_peak_glow_boost", _PEAK_GLOW_BOOST)
        self._set_uniform(prog, "u_audio_shape_power", _AUDIO_SHAPE_POWER)
        self._set_uniform(prog, "u_grid_color", _GRID_COLOR)
        self._set_uniform(prog, "u_vignette_amount", _VIGNETTE_AMOUNT)
        self._set_uniform(prog, "u_spark_count_f", float(_SPARK_COUNT))
        self._set_uniform(prog, "u_spark_base_gain", _SPARK_BASE_GAIN)
        self._set_uniform(prog, "u_grid_bass_gain", _GRID_BASS_GAIN)
        self._set_uniform(prog, "u_demo_pulse_amp", _DEMO_PULSE_AMP)
        self._set_uniform(prog, "u_demo_bass_amp", _DEMO_BASS_AMP)

    def draw(self, ctx: RenderContext) -> None:
        gl: moderngl.Context = ctx.canvas

        if self._program is None:
            self._program = gl.program(vertex_shader=_VERT, fragment_shader=_FRAG)
            vbo = gl.buffer(_QUAD.tobytes())
            self._vao = gl.simple_vertex_array(self._program, vbo, "in_vert")
            self._set_layout_constants(self._program)

        prog = self._program
        n = self.bar_count
        eq_width, eq_base_y, eq_max_height, eff_bars, eff_leds = _adaptive_layout(
            self._bounds_w,
            self._bounds_h,
            n,
            self.led_count,
        )
        demo_mode = not self.bus_active_for_draw(ctx)

        if demo_mode:
            bar_heights = np.zeros(_MAX_BARS, dtype="f4")
            bass = 0.0
        elif self._bar_history.shape[0] > 0:
            f = max(0, min(ctx.time.frame, self._bar_history.shape[0] - 1))
            bar_heights = self._bar_history[f]
            bass = float(self._bass_history[f]) if self._bass_history.size else 0.0
        else:
            bar_heights = np.zeros(_MAX_BARS, dtype="f4")
            bar_heights[:n] = self._runtime_bar_heights(ctx, n)
            bass = self.scale_audio(float(ctx.audio_bus_frame.bass))

        if eff_bars < n:
            bar_heights = _resample_bars(bar_heights, n, eff_bars)

        lr, lg, lb, _ = resolve_color(self.color_low, ctx.job.colors).rgba
        hr, hg, hb, _ = resolve_color(self.color_high, ctx.job.colors).rgba

        self._set_uniform(prog, "u_res", (self._bounds_w, self._bounds_h))
        self._set_uniform(prog, "u_origin", (self._bounds_x, self._bounds_y))
        self._set_uniform(prog, "u_canvas_h", self._canvas_h)
        self._set_uniform(prog, "u_eff_t", float(ctx.time.t) * float(self.speed))
        self._set_uniform(prog, "u_eq_width", eq_width)
        self._set_uniform(prog, "u_eq_base_y", eq_base_y)
        self._set_uniform(prog, "u_eq_max_height", eq_max_height)
        self._set_uniform(prog, "u_bar_count_f", float(eff_bars))
        self._set_uniform(prog, "u_led_count_f", float(eff_leds))
        self._set_uniform(prog, "u_bass", bass)
        self._set_uniform(prog, "u_demo_mode", 1.0 if demo_mode else 0.0)
        self._set_uniform(prog, "u_color_low", (lr, lg, lb))
        self._set_uniform(prog, "u_color_high", (hr, hg, hb))
        self._set_uniform(prog, "u_grid_intensity", float(self.grid_intensity))
        self._set_uniform(prog, "u_reflection_strength", float(self.reflection_strength))
        self._set_uniform(prog, "u_spark_intensity", float(self.spark_intensity))
        self._set_uniform(prog, "u_vignette", float(self.vignette))

        self._set_bar_heights(prog, bar_heights, eff_bars)

        gl.scissor = (
            int(self._bounds_x),
            int(ctx.job.height - self._bounds_y - ctx.bounds.height),
            int(self._bounds_w),
            int(ctx.bounds.height),
        )

        assert self._vao is not None
        self._vao.render(moderngl.TRIANGLES)

        gl.scissor = None
