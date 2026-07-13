"""Dual-plane particle fly-through background — port of "starDust" by Dmitry Andreev (Shadertoy).

Original shader: Shadertoy intro by and'2014 (CC BY-NC-SA 3.0).
Hybrid loop: steady-state particle lanes with bus-driven horizon flashes and sparkles.
Theme-aware warm/cool palette replaces the original orange/blue hardcoding.
"""

from __future__ import annotations

from typing import Any, ClassVar, cast

import moderngl
import numpy as np
from pydantic import Field, PrivateAttr

from pixfabrica_core.audio.bus import AudioBusFrame
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
from pixfabrica_std.mesh.shader_helper import precompute_bus_drives

_VERT = """
#version 330 core
in vec2 in_vert;
void main() { gl_Position = vec4(in_vert, 0.0, 1.0); }
"""

_FRAG = """
#version 330 core

// ── Tuning constants (dev adjustments) ───────────────────────────────────────
#define PLANE_COUNT         2
#define MAX_LAYERS          64
#define FAR_DIST            10000.0
#define ORIG_SPEED          1.7
#define TIME_NUMERATOR      2.0
#define PLANE_BASE          100.0
#define PLANE_SPACING       20.0
#define LANE_QUANT          100.0
#define BASE_BRIGHTNESS     0.2
#define BASS_FOV_GAIN       0.15
#define BASS_BRIGHT_GAIN    0.8
#define AMP_BRIGHT_GAIN     0.4
#define HIGH_PALETTE_BIAS   0.25
#define BEAT_HORIZON_GAIN   2.0
#define BEAT_SPARKLE_GAIN   8.0
#define SPARKLE_POPULATION  0.97
#define VIGNETTE_STRENGTH   1.4
#define VIGNETTE_GAIN       1.5
#define TILT_RATE           0.2
#define TILT_AMP            0.2
#define VIEW_SWAY_X         0.25
#define VIEW_SWAY_Y         0.25
#define WARP1_AMP           0.2
#define WARP2_AMP           0.1
#define WARP1_RATE          0.03
#define WARP2_RATE          0.04
#define SHARPNESS_MIN_X     60.0
#define SHARPNESS_MIN_Y     0.8
#define SHARPNESS_MAX_X     800.0
#define SHARPNESS_MAX_Y     3.0
#define SHARPNESS_CYCLE     0.2
#define FOV_X_RATE          0.125
#define FOV_Y_RATE          0.25
#define PALETTE_CYCLE       0.5

uniform vec2  u_res;
uniform vec2  u_origin;
uniform float u_canvas_h;
uniform float u_eff_t;
uniform float u_layers;
uniform vec3  u_color_warm;
uniform vec3  u_color_cool;
uniform float u_brightness;
uniform float u_luma_alpha;
uniform float u_opacity;
uniform float u_bus_mix;
uniform float u_bass;
uniform float u_high;
uniform float u_amplitude;
uniform float u_beat_flash;

out vec4 frag_color;

// starDust by Dmitry Andreev (and'2014) — CC BY-NC-SA 3.0.
// Pixfabrica: hybrid loop, theme palette, bus accents, layer budget.

float saturate(float x) {
    return clamp(x, 0.0, 1.0);
}

float isectPlane(vec3 n, float d, vec3 org, vec3 dir) {
    float denom = dot(dir, n);
    if (abs(denom) < 1e-6) return -1.0;
    return -(dot(org, n) + d) / denom;
}

void main() {
    float px = gl_FragCoord.x - u_origin.x;
    float py = (u_canvas_h - gl_FragCoord.y) - u_origin.y;

    if (px < 0.0 || px >= u_res.x || py < 0.0 || py >= u_res.y) discard;

    vec2 uv = vec2(px, py) / u_res;
    float time = u_eff_t;
    float bus = u_bus_mix;

    vec3 org = vec3(0.0);
    vec3 dir = vec3(uv.xy * 2.0 - 1.0, 1.0);

    float ang = sin(time * TILT_RATE) * TILT_AMP;
    vec3 odir = dir;
    dir.x = cos(ang) * odir.x + sin(ang) * odir.y;
    dir.y = sin(ang) * odir.x - cos(ang) * odir.y;

    float fov_x = 1.5 + 0.5 * sin(time * FOV_X_RATE);
    float fov_y = 1.5 + 0.5 * cos(time * FOV_Y_RATE + 0.5);
    dir.x *= fov_x * (1.0 + u_bass * BASS_FOV_GAIN * bus);
    dir.y *= fov_y * (1.0 + u_bass * BASS_FOV_GAIN * bus);

    dir.x += VIEW_SWAY_X * sin(time * 0.3);
    dir.y += VIEW_SWAY_Y * sin(time * 0.7);

    float bend1 = 0.5 + 0.5 * sin(time * WARP1_RATE);
    float bend2 = 0.5 + 0.5 * sin(time * WARP2_RATE + 1.0);
    dir.xy = mix(vec2(dir.x + WARP1_AMP * cos(dir.y) - 0.1, dir.y), dir.xy, bend1);
    dir.xy = mix(vec2(dir.x + WARP2_AMP * sin(4.0 * (dir.x + time)), dir.y), dir.xy, bend2);

    vec2 param = mix(
        vec2(SHARPNESS_MIN_X, SHARPNESS_MIN_Y),
        vec2(SHARPNESS_MAX_X, SHARPNESS_MAX_Y),
        pow(0.5 + 0.5 * sin(time * SHARPNESS_CYCLE), 2.0)
    );

    vec3 clr = vec3(0.0);

    for (int k = 0; k < PLANE_COUNT; k++) {
        for (int i = 0; i < MAX_LAYERS; i++) {
            if (float(i) >= u_layers) break;

            vec3 pn = vec3(k > 0 ? -1.0 : 1.0, 0.0, 0.0);
            float t = isectPlane(pn, PLANE_BASE + float(i) * PLANE_SPACING, org, dir);

            if (t <= 0.0 || t >= FAR_DIST) continue;

            vec3 p = org + dir * t;
            vec3 vdir = normalize(-p);
            vec3 pp = ceil(p / LANE_QUANT) * LANE_QUANT;

            float n = pp.y + float(i) + float(k) * 123.0;
            float q = fract(sin(n * 123.456) * 234.345);
            float q2 = fract(sin(n * 234.123) * 345.234);

            q = sin(p.z * 0.0003 + time * (0.25 + 0.75 * q2) + q * 12.0);
            q = saturate(q * param.x - param.x + 1.0) * param.y;
            q *= saturate(4.0 - 8.0 * abs(-50.0 + pp.y - p.y) / LANE_QUANT);
            q *= 1.0 - saturate(pow(t / FAR_DIST, 5.0));

            float fn = 1.0 - pow(1.0 - dot(vdir, pn), 2.0);
            q *= 2.0 * smoothstep(0.0, 1.0, fn);

            float palette_mix = clamp(
                0.5 + 0.5 * sin(time * PALETTE_CYCLE + q2) + u_high * HIGH_PALETTE_BIAS * bus,
                0.0,
                1.0
            );
            vec3 particle_col = mix(u_color_warm, u_color_cool, palette_mix);
            clr += q * particle_col;

            if (q2 > SPARKLE_POPULATION) {
                float sparkle = u_beat_flash * bus * (0.5 + 0.5 * sin(time * 8.0 + q2 * 20.0));
                clr += q * BEAT_SPARKLE_GAIN * sparkle * particle_col;
            }
        }
    }

    clr *= BASE_BRIGHTNESS * u_brightness
        * (1.0 + u_bass * BASS_BRIGHT_GAIN * bus)
        * (1.0 + u_amplitude * AMP_BRIGHT_GAIN * bus);

    float h = normalize(dir).x;
    clr *= 1.0 + BEAT_HORIZON_GAIN * u_beat_flash * bus * pow(saturate(1.0 - abs(h)), 8.0);

    clr *= clr;
    clr *= VIGNETTE_STRENGTH;
    clr *= 1.0 - VIGNETTE_GAIN * dot(uv - 0.5, uv - 0.5);
    clr = sqrt(max(vec3(0.0), clr));

    float luma = dot(clr, vec3(0.299, 0.587, 0.114));
    float alpha = mix(1.0, clamp(luma, 0.0, 1.0), u_luma_alpha) * u_opacity;
    frag_color = vec4(clr * alpha, alpha);
}
"""

_QUAD = np.array(
    [-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0],
    dtype="f4",
)

_ORIGINAL_TIME_SCALE = 2.0 / 1.7


def _precompute_beat_decay(
    frames: list[AudioBusFrame] | None,
    total: int,
) -> np.ndarray:
    history = np.zeros(max(total, 0), dtype=np.float32)
    if total <= 0 or not frames:
        return history
    n_bus = min(total, len(frames))
    d = 0.0
    for f in range(total):
        if f < n_bus:
            d = 1.0 if frames[f].beat else d * 0.85
        else:
            d *= 0.85
        history[f] = d
    return history


class StarDustGL(AudioVisualMixin, ClipGL):
    """Particle lanes fly past on dual mirrored planes — warm/cool theme gradient,
    bass-driven FOV pulse, beat-triggered horizon flash and sparkle bursts."""

    clip_type: ClassVar[str] = "std-star-dust-gl"
    clip_license: ClassVar[str] = "CC-BY-NC-SA-3.0"
    clip_category: ClassVar[ClipCategory] = ClipCategory.BACKGROUND
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED, ClipTag.GL, ClipTag.AUDIO_REACTIVE]
    clip_presets: ClassVar[list[ClipPreset]] = [
        ClipPreset(
            id="background",
            label="Background",
            values={
                "speed": 1.0,
                "brightness": 1.0,
                "layers": 16,
                "luma_alpha": 0.0,
                "opacity": 1.0,
            },
        ),
        ClipPreset(
            id="overlay",
            label="Overlay",
            values={
                "speed": 1.0,
                "brightness": 1.0,
                "layers": 16,
                "luma_alpha": 1.0,
                "opacity": 1.0,
            },
        ),
        ClipPreset(
            id="performance",
            label="Performance",
            values={
                "speed": 1.0,
                "brightness": 1.0,
                "layers": 8,
                "luma_alpha": 0.0,
                "opacity": 1.0,
            },
        ),
    ]

    color_warm: ColorToken | Color = color_field(ColorToken.PRIMARY)
    color_cool: ColorToken | Color = color_field(ColorToken.SECONDARY)
    speed: float = Field(
        default=1.0,
        ge=0.1,
        le=3.0,
        multiple_of=0.1,
        description="Animation speed multiplier (1 = original pacing)",
    )
    brightness: float = Field(
        default=1.0,
        ge=0.2,
        le=3.0,
        multiple_of=0.1,
        description="Overall brightness multiplier",
    )
    layers: int = Field(
        default=16,
        ge=8,
        le=32,
        multiple_of=1,
        description="Depth slices per plane (8 = fastest, 32 = densest)",
    )
    luma_alpha: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Luma-based transparency (0 = solid fill, 1 = dark areas transparent)",
    )
    opacity: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Overall layer opacity",
    )
    bus_intensity: float = Field(
        default=1.0,
        ge=0.0,
        le=2.0,
        multiple_of=0.1,
        description="Audio bus reactivity — bass FOV/brightness, beat horizon/sparkle (0 = off)",
    )
    sensitivity: float = Field(
        default=2.5,
        ge=0.1,
        le=8.0,
        multiple_of=0.1,
        description="Audio response gain on bass/high/amplitude after job-wide normalization",
    )

    _canvas_h: float = PrivateAttr(default=0.0)
    _bounds_x: float = PrivateAttr(default=0.0)
    _bounds_y: float = PrivateAttr(default=0.0)
    _bounds_w: float = PrivateAttr(default=0.0)
    _bounds_h: float = PrivateAttr(default=0.0)
    _bass_history: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype="f4"))
    _high_history: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype="f4"))
    _amp_history: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype="f4"))
    _beat_decay_frames: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype="f4"))
    _program: moderngl.Program | None = PrivateAttr(default=None)
    _vao: moderngl.VertexArray | None = PrivateAttr(default=None)

    async def prepare(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        b = bounds or Rect(0, 0, ctx.job.width, ctx.job.height)
        self._canvas_h = float(ctx.job.height)
        self._bounds_x = float(b.x)
        self._bounds_y = float(b.y)
        self._bounds_w = float(b.width)
        self._bounds_h = float(b.height)

        bus = self.bus_timeline(ctx)
        total = max(ctx.job.total_frames, 0)
        self._bass_history, _, self._high_history, self._amp_history = precompute_bus_drives(
            bus,
            total,
        )
        self._beat_decay_frames = _precompute_beat_decay(bus, total)

    def _set_uniform(self, prog: moderngl.Program, name: str, value: Any) -> None:
        cast(moderngl.Uniform, prog[name]).value = value

    def _audio_drives_for_frame(
        self,
        ctx: RenderContext,
    ) -> tuple[float, float, float, float]:
        if not self.bus_active_for_draw(ctx):
            return 0.0, 0.0, 0.0, 0.0
        sens = float(self.sensitivity)
        if self._bass_history.shape[0] > 0:
            f = max(0, min(ctx.time.frame, self._bass_history.shape[0] - 1))
            bass = min(1.0, float(self._bass_history[f]) * sens)
            high = min(1.0, float(self._high_history[f]) * sens)
            amp = min(1.0, float(self._amp_history[f]) * sens)
            beat_flash = (
                float(self._beat_decay_frames[f]) if self._beat_decay_frames.shape[0] > 0 else 0.0
            )
        else:
            af = ctx.audio_bus_frame
            bass = self.scale_audio(float(af.bass))
            high = self.scale_audio(float(af.high))
            amp = self.scale_audio(float(af.amplitude))
            beat_flash = 1.0 if af.beat else 0.0
        return bass, high, amp, beat_flash

    def draw(self, ctx: RenderContext) -> None:
        gl: moderngl.Context = ctx.canvas

        if self._program is None:
            self._program = gl.program(vertex_shader=_VERT, fragment_shader=_FRAG)
            vbo = gl.buffer(_QUAD.tobytes())
            self._vao = gl.simple_vertex_array(self._program, vbo, "in_vert")

        prog = self._program
        bass, high, amp, beat_flash = self._audio_drives_for_frame(ctx)
        bus_mix = float(self.bus_intensity)

        self._set_uniform(prog, "u_res", (self._bounds_w, self._bounds_h))
        self._set_uniform(prog, "u_origin", (self._bounds_x, self._bounds_y))
        self._set_uniform(prog, "u_canvas_h", self._canvas_h)
        self._set_uniform(prog, "u_eff_t", ctx.time.t * self.speed * _ORIGINAL_TIME_SCALE)
        self._set_uniform(prog, "u_layers", float(self.layers))

        wr, wg, wb, _ = resolve_color(self.color_warm, ctx.job.colors).rgba
        cr, cg, cb, _ = resolve_color(self.color_cool, ctx.job.colors).rgba
        self._set_uniform(prog, "u_color_warm", (wr, wg, wb))
        self._set_uniform(prog, "u_color_cool", (cr, cg, cb))

        self._set_uniform(prog, "u_brightness", self.brightness)
        self._set_uniform(prog, "u_luma_alpha", self.luma_alpha)
        self._set_uniform(prog, "u_opacity", self.opacity)
        self._set_uniform(prog, "u_bus_mix", bus_mix)
        self._set_uniform(prog, "u_bass", bass)
        self._set_uniform(prog, "u_high", high)
        self._set_uniform(prog, "u_amplitude", amp)
        self._set_uniform(prog, "u_beat_flash", beat_flash)

        gl.scissor = (
            int(self._bounds_x),
            int(ctx.job.height - self._bounds_y - ctx.bounds.height),
            int(self._bounds_w),
            int(self._bounds_h),
        )

        assert self._vao is not None
        self._vao.render(moderngl.TRIANGLES)

        gl.scissor = None
