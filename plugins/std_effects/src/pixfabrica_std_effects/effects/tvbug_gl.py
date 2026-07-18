"""Bounds-local GL TV Bug - full-bleed CRT glitch with scanlines and RGB flicker."""

from __future__ import annotations

from typing import Any, ClassVar

import moderngl
import numpy as np
from pydantic import Field, PrivateAttr

from pixfabrica_core.clips import ClipCategory, ClipTag, PrepareContext
from pixfabrica_core.composition.effect_def import EffectContext, GLEffect, set_gl_src_uv_uniforms
from pixfabrica_core.graphics import Rect

# ---------------------------------------------------------------------------
# Tunable defaults - passed to the shader as uniforms each frame.
# ---------------------------------------------------------------------------
_UV_MARGIN = 0.06
_DEFAULT_OPACITY = 1.0
_DEFAULT_FREQUENCY = 11.0
_FREQUENCY_MIN = 4.0
_FREQUENCY_MAX = 24.0

_VERT = """
#version 330 core
in vec2 in_vert;
out vec2 v_uv;
void main() {
    v_uv = in_vert * 0.5 + 0.5;
    gl_Position = vec4(in_vert, 0.0, 1.0);
}
"""

_FRAG = """
#version 330 core

uniform sampler2D u_source;
uniform float u_time;
uniform float u_frequency;
uniform float u_opacity;
uniform vec2 u_resolution;
uniform vec2 u_src_scale;
uniform vec2 u_src_bias;

in vec2 v_uv;
out vec4 fragColor;

const float HASH_A = 12.9898;
const float HASH_B = 78.233;
const float HASH_SCALE_2D = 43758.5453;
const float HASH_SCALE_1D = 43758.5453123;

const float FLICK_TIME_RATE = 10.0;
const float FLICK_SNOISE_A = 2000.0;
const float FLICK_SNOISE_B = 3000.0;
const float FLICK_THRESHOLD = 0.85;
const float FLICK_OFFSET = 0.05;

const float DESATURATE_MIX = 0.95;
const float COLOR_GAMMA = 1.5;
const float COLOR_GAMMA_G_DELTA = 0.1;

const float YBUG_SNOISE_SEED = 200.0;
const float YBUG_TIME_RATE = 2.0;
const float YBUG_SCALE = 14.0;
const float YBUG_MAX_SHIFT = 2.0;

const float HSTRIP_VNOISE_TIME_RATE = 6.0;
const float HSTRIP_HNOISE_TIME_RATE = 10.0;
const float HSTRIP_HNOISE_THRESHOLD = 0.5;
const float HSTRIP_LINE_FREQ = 10.0;
const float HSTRIP_LINE_CLAMP_LO = 0.9;
const float HSTRIP_LINE_CLAMP_HI = 1.0;
const float HSTRIP_LINE_REMAP = 10.0;
const float HSTRIP_SHIFT = 0.03;

const float GRAIN_THRESHOLD = 0.7;
const float GRAIN_DISPLACE = 0.05;
const float GRAIN_SNOISE_SEED = 500.0;
const float GRAIN_TIME_SEED = 100.0;
const float GRAIN_UV_SCALE = 0.01;

const float SCAN_PI = 3.1415;
const float SCAN_Y_DIVISOR = 2.7;
const float SCAN_BASE = 0.75;
const float SCAN_WEIGHT = 0.25;

const float BLINK_BASE = 0.96;
const float BLINK_AMP = 0.04;
const float BLINK_TIME_RATE = 100.0;

const float VIG_SCALE = 44.0;
const float VIG_RAND_LO = 0.7;
const float VIG_RAND_HI = 1.0;
const float VIG_COLOR_BASE = 0.6;
const float VIG_COLOR_WEIGHT = 0.4;
const float VIG_RAND_OFFSET = 0.5;

const float DIRTY_WEIGHT = 0.2;

float rand2d(vec2 co) {
    return fract(sin(dot(co.xy, vec2(HASH_A, HASH_B))) * HASH_SCALE_2D);
}

float rand(float n) {
    return fract(sin(n) * HASH_SCALE_1D);
}

float noise(float p) {
    float fl = floor(p);
    float fc = fract(p);
    return mix(rand(fl), rand(fl + 1.0), fc);
}

float map_range(float val, float amin, float amax, float bmin, float bmax) {
    float n = (val - amin) / (amax - amin);
    return bmin + n * (bmax - bmin);
}

float snoise(float p) {
    return map_range(noise(p), 0.0, 1.0, -1.0, 1.0);
}

float threshold(float val, float cut) {
    float v = clamp(abs(val) - cut, 0.0, 1.0);
    v = sign(val) * v;
    float scale = 1.0 / (1.0 - cut);
    return v * scale;
}

vec2 to_src_uv(vec2 uv) {
    return uv * u_src_scale + u_src_bias;
}

vec4 sample_src(vec2 uv) {
    vec2 src_uv = to_src_uv(uv);
    if (src_uv.x < 0.0 || src_uv.x > 1.0 || src_uv.y < 0.0 || src_uv.y > 1.0) {
        return vec4(0.0);
    }
    return texture(u_source, src_uv);
}

vec3 sample_color(vec2 uv) {
    vec3 color = sample_src(uv).rgb;
    float bw = (color.r + color.g + color.b) / 3.0;
    color = mix(color, vec3(bw, bw, bw), DESATURATE_MIX);
    color.r = pow(color.r, COLOR_GAMMA);
    color.g = pow(color.g, COLOR_GAMMA - COLOR_GAMMA_G_DELTA);
    color.b = pow(color.b, COLOR_GAMMA);
    return color;
}

vec3 ghost(vec2 uv) {
    float n1 = threshold(snoise(u_time * FLICK_TIME_RATE), FLICK_THRESHOLD);
    float n2 = threshold(snoise(FLICK_SNOISE_A + u_time * FLICK_TIME_RATE), FLICK_THRESHOLD);
    float n3 = threshold(snoise(FLICK_SNOISE_B + u_time * FLICK_TIME_RATE), FLICK_THRESHOLD);

    vec2 orv = vec2(n1 * FLICK_OFFSET, 0.0);
    vec2 og = vec2(n2 * FLICK_OFFSET, 0.0);
    vec2 ob = vec2(0.0, n3 * FLICK_OFFSET);

    float r = sample_color(uv + orv).r;
    float g = sample_color(uv + og).g;
    float b = sample_color(uv + ob).b;
    return vec3(r, g, b);
}

vec2 uv_ybug(vec2 uv) {
    float n4 = clamp(noise(YBUG_SNOISE_SEED + u_time * YBUG_TIME_RATE) * YBUG_SCALE, 0.0, YBUG_MAX_SHIFT);
    uv.y += n4;
    uv.y = mod(uv.y, 1.0);
    return uv;
}

vec2 uv_hstrip(vec2 uv) {
    float vnoise = snoise(u_time * HSTRIP_VNOISE_TIME_RATE);
    float hnoise = threshold(snoise(u_time * HSTRIP_HNOISE_TIME_RATE), HSTRIP_HNOISE_THRESHOLD);

    float line = (sin(uv.y * HSTRIP_LINE_FREQ + vnoise) + 1.0) / 2.0;
    line = (clamp(line, HSTRIP_LINE_CLAMP_LO, HSTRIP_LINE_CLAMP_HI) - HSTRIP_LINE_CLAMP_LO)
        * HSTRIP_LINE_REMAP;

    uv.x += line * HSTRIP_SHIFT * hnoise;
    uv.x = mod(uv.x, 1.0);
    return uv;
}

void main() {
    float t = float(int(u_time * u_frequency));
    vec2 uv = v_uv;
    vec2 ouv = uv;

    float xn = threshold(snoise(u_time * FLICK_TIME_RATE), GRAIN_THRESHOLD) * GRAIN_DISPLACE;
    float yn = threshold(snoise((GRAIN_SNOISE_SEED + u_time) * FLICK_TIME_RATE), GRAIN_THRESHOLD) * GRAIN_DISPLACE;
    float r = rand2d(uv + (t + GRAIN_TIME_SEED) * GRAIN_UV_SCALE);
    uv = uv + vec2(xn, yn) * r;

    uv = uv_ybug(uv);
    uv = uv_hstrip(uv);

    vec3 color = ghost(uv);

    float scan_a = (sin(uv.y * SCAN_PI * u_resolution.y / SCAN_Y_DIVISOR) + 1.0) / 2.0;
    color *= SCAN_BASE + scan_a * SCAN_WEIGHT;

    float blink = BLINK_BASE + BLINK_AMP * (sin(u_time * BLINK_TIME_RATE) + 1.0) / 2.0;
    color *= blink;

    float vig = VIG_SCALE * (ouv.x * (1.0 - ouv.x) * ouv.y * (1.0 - ouv.y));
    vig *= mix(VIG_RAND_LO, VIG_RAND_HI, rand(t + VIG_RAND_OFFSET));
    color *= VIG_COLOR_BASE + VIG_COLOR_WEIGHT * vig;

    color *= 1.0 + rand2d(uv + t * GRAIN_UV_SCALE) * DIRTY_WEIGHT;

    vec4 original = sample_src(v_uv);
    fragColor = vec4(mix(original.rgb, color, u_opacity), original.a);
}
"""

_QUAD = np.array(
    [-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0],
    dtype="f4",
)


class TvbugGL(GLEffect):
    """Full-bleed CRT glitch with scanlines, RGB flicker, and vertical tear."""

    uv_margin: ClassVar[float] = _UV_MARGIN
    effect_type: ClassVar[str] = "std-tvbug-gl"
    clip_category: ClassVar[ClipCategory] = ClipCategory.EFFECTS
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED, ClipTag.GL]

    opacity: float = Field(
        default=_DEFAULT_OPACITY,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Blend between original (0) and glitched (1)",
    )
    frequency: float = Field(
        default=_DEFAULT_FREQUENCY,
        ge=_FREQUENCY_MIN,
        le=_FREQUENCY_MAX,
        multiple_of=0.5,
        description="Grain and flicker update rate (higher = faster stepping)",
    )

    _program: moderngl.Program | None = PrivateAttr(default=None)
    _vao: moderngl.VertexArray | None = PrivateAttr(default=None)

    async def prepare(self, _ctx: PrepareContext, _bounds: Rect | None = None) -> None:
        pass

    def _set_uniform(self, prog: moderngl.Program, name: str, value: Any) -> None:
        if name in prog:
            member = prog[name]
            if isinstance(member, moderngl.Uniform):
                member.value = value

    def apply(self, ctx: EffectContext) -> None:
        source = ctx.source
        target = ctx.target
        if source is None:
            return

        opacity = float(self.opacity)

        gl: moderngl.Context = target.ctx
        if self._program is None:
            self._program = gl.program(vertex_shader=_VERT, fragment_shader=_FRAG)
            vbo = gl.buffer(_QUAD.tobytes())
            self._vao = gl.simple_vertex_array(self._program, vbo, "in_vert")

        assert self._program is not None
        assert self._vao is not None
        w = max(float(ctx.bounds.width), 1.0)
        h = max(float(ctx.bounds.height), 1.0)
        target.use()
        source.use(location=0)
        self._set_uniform(self._program, "u_source", 0)
        self._set_uniform(self._program, "u_time", float(ctx.time.t))
        self._set_uniform(self._program, "u_frequency", float(self.frequency))
        self._set_uniform(self._program, "u_opacity", opacity)
        self._set_uniform(self._program, "u_resolution", (w, h))
        set_gl_src_uv_uniforms(self._program, ctx)
        self._vao.render(moderngl.TRIANGLES)
