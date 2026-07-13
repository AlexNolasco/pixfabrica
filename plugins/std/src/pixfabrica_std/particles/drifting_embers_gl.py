"""Drifting embers overlay — faint smoke, bottom heat glow, and rising ember particles."""

from __future__ import annotations

from typing import Any, ClassVar

import moderngl
import numpy as np
from pydantic import Field, PrivateAttr

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

# ---------------------------------------------------------------------------
# Tunable defaults — adjust here; passed to the shader as uniforms each frame.
# ---------------------------------------------------------------------------
_MAX_EMBERS = 64
_EMBER_LOOP_CAP = 64

# Smoke (fbm)
_SMOKE_COLOR = (0.08, 0.05, 0.05)
_SMOKE_UV_SCALE = 1.5
_SMOKE_DRIFT_SPEED = 0.5
_FBM_WIND_SPEED = 2.0
_FBM_OCTAVES = 5
_SMOKE_BASS_GAIN = 0.5

# Bottom ambient heat
_HEAT_COLOR = (0.2, 0.05, 0.01)
_HEAT_EDGE_FALLOFF = 3.0
_HEAT_EDGE_OFFSET = 1.5
_HEAT_BASS_GAIN = 1.5

# Embers
_EMBER_GLOW_GAIN = 0.0015
_EMBER_SCATTER = 2.5
_EMBER_SPEED_MIN = 0.15
_EMBER_SPEED_RANGE = 0.25
_EMBER_BASS_FLASH = 0.8
_EMBER_BASE_BRIGHTNESS = 0.5

# Vignette / demo
_VIGNETTE_AMOUNT = 0.4
_DEMO_BASS_SPEED = 2.0
_DEMO_BASS_AMP = 0.2

# Campfire preset ember endpoints (original Shadertoy mix)
_CAMPFIRE_EMBER_HOT_HEX = "#FF9900"
_CAMPFIRE_EMBER_COOL_HEX = "#CC1A00"

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
uniform float u_bass;
uniform float u_demo_mode;

uniform vec3  u_color_ember_hot;
uniform vec3  u_color_ember_cool;

uniform float u_smoke_intensity;
uniform float u_heat_intensity;
uniform float u_ember_intensity;
uniform float u_vignette;
uniform float u_ember_count_f;
uniform float u_luma_alpha;
uniform float u_opacity;

uniform vec3  u_smoke_color;
uniform float u_smoke_uv_scale;
uniform float u_smoke_drift_speed;
uniform float u_fbm_wind_speed;
uniform vec3  u_heat_color;
uniform float u_heat_edge_falloff;
uniform float u_heat_edge_offset;
uniform float u_heat_bass_gain;
uniform float u_smoke_bass_gain;
uniform float u_ember_glow_gain;
uniform float u_ember_scatter;
uniform float u_ember_speed_min;
uniform float u_ember_speed_range;
uniform float u_ember_bass_flash;
uniform float u_ember_base_brightness;
uniform float u_vignette_amount;
uniform float u_demo_bass_speed;
uniform float u_demo_bass_amp;

out vec4 frag_color;

float hash(vec2 p) {
    p = fract(p * vec2(123.34, 456.21));
    p += dot(p, p + 45.32);
    return fract(p.x * p.y);
}

float noise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    float a = hash(i);
    float b = hash(i + vec2(1.0, 0.0));
    float c = hash(i + vec2(0.0, 1.0));
    float d = hash(i + vec2(1.0, 1.0));
    return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
}

float fbm(vec2 p, float eff_t) {
    float f = 0.0;
    float amp = 0.5;
    for (int i = 0; i < 5; i++) {
        f += amp * noise(p);
        p *= 2.0;
        p.y -= eff_t * u_fbm_wind_speed;
        amp *= 0.5;
    }
    return f;
}

void main() {
    float px = gl_FragCoord.x - u_origin.x;
    float py = (u_canvas_h - gl_FragCoord.y) - u_origin.y;

    vec2 uv = (vec2(px, py) - u_res * 0.5) / u_res.y;
    uv.y = -uv.y;

    float bass = u_bass;
    if (u_demo_mode > 0.5 && bass < 0.01) {
        bass = (sin(u_eff_t * u_demo_bass_speed) * 0.5 + 0.5) * u_demo_bass_amp;
    }

    vec3 col = vec3(0.0);

    if (u_smoke_intensity > 0.0) {
        float smoke = fbm(uv * u_smoke_uv_scale + vec2(0.0, -u_eff_t * u_smoke_drift_speed), u_eff_t);
        col += u_smoke_color * smoke * (1.0 + bass * u_smoke_bass_gain) * u_smoke_intensity;
    }

    if (u_heat_intensity > 0.0) {
        col += u_heat_color * exp(-uv.y * u_heat_edge_falloff - u_heat_edge_offset)
             * (1.0 + bass * u_heat_bass_gain) * u_heat_intensity;
    }

    if (u_ember_intensity > 0.0) {
        int emberCount = int(u_ember_count_f);
        for (int i = 0; i < 64; i++) {
            if (i >= emberCount) break;
            float fi = float(i);
            float t = u_eff_t * (u_ember_speed_min + hash(vec2(fi)) * u_ember_speed_range) + fi * 1.23;

            float xOffset = (noise(vec2(t, fi)) - 0.5) * u_ember_scatter;
            vec2 pUv = vec2(xOffset, fract(t) * 2.0 - 1.0);

            float dist = length(uv - pUv);
            float glow = (u_ember_glow_gain / max(dist, 1e-4))
                       * (u_ember_base_brightness + bass * u_ember_bass_flash);
            glow *= smoothstep(1.0, 0.8, fract(t)) * smoothstep(0.0, 0.2, fract(t));

            vec3 emberColor = mix(u_color_ember_hot, u_color_ember_cool, fract(t));
            col += emberColor * glow * u_ember_intensity;
        }
    }

    if (u_vignette > 0.0) {
        col *= 1.0 - dot(uv, uv) * u_vignette_amount * u_vignette;
    }

    col = pow(col, vec3(1.0 / 2.2));

    float coverage = clamp(max(col.r, max(col.g, col.b)), 0.0, 1.0);
    float alpha = mix(1.0, coverage, u_luma_alpha) * u_opacity;
    frag_color = vec4(col * alpha, alpha);
}
"""

_QUAD = np.array(
    [-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0],
    dtype="f4",
)


class DriftingEmbersGL(AudioVisualMixin, ClipGL):
    """Atmospheric ember overlay — faint rising smoke, bottom heat glow, and soft
    drifting particles. Transparent except where the effect is bright."""

    clip_type: ClassVar[str] = "std-drifting-embers-gl"
    clip_category: ClassVar[ClipCategory] = ClipCategory.PARTICLES
    clip_tags: ClassVar[list[str]] = [
        ClipTag.ANIMATED,
        ClipTag.GL,
        ClipTag.AUDIO_REACTIVE,
        ClipTag.PARTICLE,
    ]
    clip_presets: ClassVar[list[ClipPreset]] = [
        ClipPreset(id="default", label="Default", values={}),
        ClipPreset(
            id="campfire",
            label="Campfire",
            values={
                "color_ember_hot": _CAMPFIRE_EMBER_HOT_HEX,
                "color_ember_cool": _CAMPFIRE_EMBER_COOL_HEX,
            },
        ),
        ClipPreset(
            id="sparse",
            label="Sparse",
            values={
                "ember_count": 16,
                "smoke_intensity": 0.5,
                "heat_intensity": 0.5,
                "ember_intensity": 0.8,
            },
        ),
    ]

    color_ember_hot: ColorToken | Color = color_field(
        ColorToken.ACCENT, default=Color(_CAMPFIRE_EMBER_HOT_HEX)
    )
    color_ember_cool: ColorToken | Color = color_field(
        ColorToken.PRIMARY, default=Color(_CAMPFIRE_EMBER_COOL_HEX)
    )
    ember_count: int = Field(
        default=40,
        ge=8,
        le=_MAX_EMBERS,
        multiple_of=1,
        description="Number of drifting ember particles",
    )
    speed: float = Field(
        default=1.0,
        ge=0.25,
        le=3.0,
        multiple_of=0.05,
        description="Global animation speed multiplier",
    )
    smoke_intensity: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.05,
        description="Background fbm smoke (0 = off)",
    )
    heat_intensity: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.05,
        description="Bottom edge ambient heat glow (0 = off)",
    )
    ember_intensity: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.05,
        description="Drifting ember particles (0 = off)",
    )
    vignette: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.05,
        description="Edge darkening (0 = off)",
    )
    luma_alpha: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Luma-based transparency (1 = dark areas transparent)",
    )
    opacity: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Overall layer opacity",
    )
    sensitivity: float = Field(
        default=2.5,
        ge=0.1,
        le=8.0,
        multiple_of=0.05,
        description="Audio response gain on bass drives after job-wide normalization",
    )

    _canvas_h: float = PrivateAttr(default=0.0)
    _bounds_x: float = PrivateAttr(default=0.0)
    _bounds_y: float = PrivateAttr(default=0.0)
    _bounds_w: float = PrivateAttr(default=0.0)
    _bounds_h: float = PrivateAttr(default=0.0)
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
        total = max(ctx.job.total_frames, 0)
        self._bass_history, _, _, _ = precompute_bus_drives(self.bus_timeline(ctx), total)

    def _set_uniform(self, prog: moderngl.Program, name: str, value: Any) -> None:
        if name not in prog:
            return
        member = prog[name]
        if isinstance(member, moderngl.Uniform):
            member.value = value

    def _set_shader_constants(self, prog: moderngl.Program) -> None:
        self._set_uniform(prog, "u_smoke_color", _SMOKE_COLOR)
        self._set_uniform(prog, "u_smoke_uv_scale", _SMOKE_UV_SCALE)
        self._set_uniform(prog, "u_smoke_drift_speed", _SMOKE_DRIFT_SPEED)
        self._set_uniform(prog, "u_fbm_wind_speed", _FBM_WIND_SPEED)
        self._set_uniform(prog, "u_heat_color", _HEAT_COLOR)
        self._set_uniform(prog, "u_heat_edge_falloff", _HEAT_EDGE_FALLOFF)
        self._set_uniform(prog, "u_heat_edge_offset", _HEAT_EDGE_OFFSET)
        self._set_uniform(prog, "u_heat_bass_gain", _HEAT_BASS_GAIN)
        self._set_uniform(prog, "u_smoke_bass_gain", _SMOKE_BASS_GAIN)
        self._set_uniform(prog, "u_ember_glow_gain", _EMBER_GLOW_GAIN)
        self._set_uniform(prog, "u_ember_scatter", _EMBER_SCATTER)
        self._set_uniform(prog, "u_ember_speed_min", _EMBER_SPEED_MIN)
        self._set_uniform(prog, "u_ember_speed_range", _EMBER_SPEED_RANGE)
        self._set_uniform(prog, "u_ember_bass_flash", _EMBER_BASS_FLASH)
        self._set_uniform(prog, "u_ember_base_brightness", _EMBER_BASE_BRIGHTNESS)
        self._set_uniform(prog, "u_vignette_amount", _VIGNETTE_AMOUNT)
        self._set_uniform(prog, "u_demo_bass_speed", _DEMO_BASS_SPEED)
        self._set_uniform(prog, "u_demo_bass_amp", _DEMO_BASS_AMP)

    def _bass_for_frame(self, ctx: RenderContext, demo_mode: bool) -> float:
        if demo_mode:
            return 0.0
        sens = float(self.sensitivity)
        if self._bass_history.shape[0] > 0:
            f = max(0, min(ctx.time.frame, self._bass_history.shape[0] - 1))
            return min(1.0, float(self._bass_history[f]) * sens)
        return self.scale_audio(float(ctx.audio_bus_frame.bass))

    def draw(self, ctx: RenderContext) -> None:
        gl: moderngl.Context = ctx.canvas

        if self._program is None:
            self._program = gl.program(vertex_shader=_VERT, fragment_shader=_FRAG)
            vbo = gl.buffer(_QUAD.tobytes())
            self._vao = gl.simple_vertex_array(self._program, vbo, "in_vert")
            self._set_shader_constants(self._program)

        prog = self._program
        demo_mode = not self.bus_active_for_draw(ctx)
        bass = self._bass_for_frame(ctx, demo_mode)

        hr, hg, hb, _ = resolve_color(self.color_ember_hot, ctx.job.colors).rgba
        cr, cg, cb, _ = resolve_color(self.color_ember_cool, ctx.job.colors).rgba

        self._set_uniform(prog, "u_res", (self._bounds_w, self._bounds_h))
        self._set_uniform(prog, "u_origin", (self._bounds_x, self._bounds_y))
        self._set_uniform(prog, "u_canvas_h", self._canvas_h)
        self._set_uniform(prog, "u_eff_t", float(ctx.time.t) * float(self.speed))
        self._set_uniform(prog, "u_bass", bass)
        self._set_uniform(prog, "u_demo_mode", 1.0 if demo_mode else 0.0)
        self._set_uniform(prog, "u_color_ember_hot", (hr, hg, hb))
        self._set_uniform(prog, "u_color_ember_cool", (cr, cg, cb))
        self._set_uniform(prog, "u_smoke_intensity", float(self.smoke_intensity))
        self._set_uniform(prog, "u_heat_intensity", float(self.heat_intensity))
        self._set_uniform(prog, "u_ember_intensity", float(self.ember_intensity))
        self._set_uniform(prog, "u_vignette", float(self.vignette))
        self._set_uniform(prog, "u_ember_count_f", float(self.ember_count))
        self._set_uniform(prog, "u_luma_alpha", float(self.luma_alpha))
        self._set_uniform(prog, "u_opacity", float(self.opacity))

        gl.scissor = (
            int(self._bounds_x),
            int(ctx.job.height - self._bounds_y - ctx.bounds.height),
            int(self._bounds_w),
            int(ctx.bounds.height),
        )

        assert self._vao is not None
        self._vao.render(moderngl.TRIANGLES)

        gl.scissor = None
