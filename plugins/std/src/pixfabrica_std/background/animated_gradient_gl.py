from __future__ import annotations

from typing import Any, ClassVar, cast

import moderngl
import numpy as np
from pydantic import Field, PrivateAttr

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
from pixfabrica_std.tilt import ANGLE_BAND_DESC, ANGLE_BAND_MAX, ANGLE_BAND_MIN

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

uniform vec3  u_color_a;
uniform vec3  u_color_b;
uniform vec3  u_color_c;
uniform vec3  u_color_d;

uniform float u_wave_speed;
uniform float u_noise_speed;
uniform float u_wave_frequency;
uniform float u_wave_amplitude;
uniform float u_wave_amplitude_y_ratio;
uniform float u_rotation_spread;
uniform float u_rotation_offset;
uniform float u_angle;
uniform float u_opacity;

out vec4 frag_color;

mat2 Rot(float a) {
    float s = sin(a);
    float c = cos(a);
    return mat2(c, -s, s, c);
}

vec2 hash(vec2 p) {
    p = vec2(dot(p, vec2(2127.1, 81.17)), dot(p, vec2(1269.5, 283.37)));
    return fract(sin(p) * 43758.5453);
}

float noise(in vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    float n = mix(
        mix(dot(-1.0 + 2.0 * hash(i + vec2(0.0, 0.0)), f - vec2(0.0, 0.0)),
            dot(-1.0 + 2.0 * hash(i + vec2(1.0, 0.0)), f - vec2(1.0, 0.0)), u.x),
        mix(dot(-1.0 + 2.0 * hash(i + vec2(0.0, 1.0)), f - vec2(0.0, 1.0)),
            dot(-1.0 + 2.0 * hash(i + vec2(1.0, 1.0)), f - vec2(1.0, 1.0)), u.x),
        u.y);
    return 0.5 + 0.5 * n;
}

void main() {
    float px = gl_FragCoord.x - u_origin.x;
    float py = (u_canvas_h - gl_FragCoord.y) - u_origin.y;

    vec2 uv = vec2(px / u_res.x, py / u_res.y);
    float ratio = u_res.x / u_res.y;

    vec2 tuv = uv - 0.5;

    float degree = noise(vec2(u_t * u_noise_speed, tuv.x * tuv.y));

    tuv.y *= 1.0 / ratio;
    tuv *= Rot(radians((degree - 0.5) * u_rotation_spread + u_rotation_offset));
    tuv.y *= ratio;

    float speed = u_t * u_wave_speed;
    tuv.x += sin(tuv.y * u_wave_frequency + speed) / u_wave_amplitude;
    tuv.y += sin(tuv.x * u_wave_frequency * 1.5 + speed) / (u_wave_amplitude * u_wave_amplitude_y_ratio);

    float tilt_rad = radians(-u_angle);
    vec3 layer1 = mix(u_color_a, u_color_b, smoothstep(-0.3, 0.2, (tuv * Rot(tilt_rad)).x));
    vec3 layer2 = mix(u_color_c, u_color_d, smoothstep(-0.3, 0.2, (tuv * Rot(tilt_rad)).x));
    vec3 col = mix(layer1, layer2, smoothstep(0.5, -0.3, tuv.y));

    frag_color = vec4(col * u_opacity, u_opacity);
}
"""

_QUAD = np.array(
    [-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0],
    dtype="f4",
)


class AnimatedGradientGL(ClipGL):
    """Animated noise-warped gradient background — two blended color layers, fully GPU-driven."""

    clip_type: ClassVar[str] = "std-animated-gradient-gl"
    clip_category: ClassVar[ClipCategory] = ClipCategory.BACKGROUND
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED, ClipTag.GRADIENT, ClipTag.GL]
    clip_presets: ClassVar[list[ClipPreset]] = [
        ClipPreset(
            id="slow_drift",
            label="Slow Drift",
            values={"wave_speed": 1.0, "noise_speed": 0.1, "wave_amplitude": 20.0, "opacity": 1.0},
        ),
        ClipPreset(
            id="frenetic",
            label="Frenetic",
            values={
                "wave_speed": 8.0,
                "noise_speed": 0.9,
                "wave_amplitude": 5.0,
                "rotation_spread": 720.0,
                "opacity": 1.0,
            },
        ),
        ClipPreset(
            id="gentle_pulse",
            label="Gentle Pulse",
            values={
                "wave_speed": 2.0,
                "noise_speed": 0.2,
                "wave_frequency": 2.0,
                "wave_amplitude": 20.0,
                "opacity": 0.8,
            },
        ),
    ]

    color_a: ColorToken | Color = color_field(ColorToken.PRIMARY)
    color_b: ColorToken | Color = color_field(ColorToken.SECONDARY)
    color_c: ColorToken | Color = color_field(ColorToken.ACCENT)
    color_d: ColorToken | Color = color_field(ColorToken.TERTIARY)

    angle: float = Field(
        default=-5.0,
        ge=ANGLE_BAND_MIN,
        le=ANGLE_BAND_MAX,
        multiple_of=1.0,
        description=ANGLE_BAND_DESC,
    )
    opacity: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Overall layer opacity",
    )
    wave_speed: float = Field(
        default=2.0, ge=0, le=10, multiple_of=1, description="Wave animation speed multiplier"
    )
    noise_speed: float = Field(
        default=0.3,
        ge=0.1,
        le=1,
        multiple_of=0.1,
        description="Noise-based rotation speed multiplier",
    )
    wave_frequency: float = Field(
        default=5.0, ge=0.1, le=5.0, multiple_of=0.1, description="Wave cycles across the frame"
    )
    wave_amplitude: float = Field(
        default=30.0, ge=0.0, le=30, multiple_of=1, description="Wave distortion strength (x-axis)"
    )
    wave_amplitude_y_ratio: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Y-axis amplitude as fraction of wave_amplitude",
    )
    rotation_spread: float = Field(
        default=720.0, ge=0, le=720, multiple_of=1, description="Rotation spread in degrees"
    )
    rotation_offset: float = Field(
        default=180.0, ge=0, le=720, multiple_of=1, description="Base rotation offset in degrees"
    )

    _canvas_h: float = PrivateAttr(default=0.0)
    _bounds_x: float = PrivateAttr(default=0.0)
    _bounds_y: float = PrivateAttr(default=0.0)
    _bounds_w: float = PrivateAttr(default=0.0)
    _bounds_h: float = PrivateAttr(default=0.0)

    _program: moderngl.Program | None = PrivateAttr(default=None)
    _vao: moderngl.VertexArray | None = PrivateAttr(default=None)

    async def prepare(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        b = bounds or Rect(0, 0, ctx.job.width, ctx.job.height)
        self._canvas_h = float(ctx.job.height)
        self._bounds_x = float(b.x)
        self._bounds_y = float(b.y)
        self._bounds_w = float(b.width)
        self._bounds_h = float(b.height)

    def _set_uniform(self, prog: moderngl.Program, name: str, value: Any) -> None:
        cast(moderngl.Uniform, prog[name]).value = value

    def draw(self, ctx: RenderContext) -> None:
        gl: moderngl.Context = ctx.canvas

        if self._program is None:
            self._program = gl.program(vertex_shader=_VERT, fragment_shader=_FRAG)
            vbo = gl.buffer(_QUAD.tobytes())
            self._vao = gl.simple_vertex_array(self._program, vbo, "in_vert")

        prog = self._program

        self._set_uniform(prog, "u_res", (self._bounds_w, self._bounds_h))
        self._set_uniform(prog, "u_origin", (self._bounds_x, self._bounds_y))
        self._set_uniform(prog, "u_canvas_h", self._canvas_h)
        self._set_uniform(prog, "u_t", ctx.time.t)

        ra, ga, ba, _ = resolve_color(self.color_a, ctx.job.colors).rgba
        rb, gb, bb, _ = resolve_color(self.color_b, ctx.job.colors).rgba
        rc, gc, bc, _ = resolve_color(self.color_c, ctx.job.colors).rgba
        rd, gd, bd, _ = resolve_color(self.color_d, ctx.job.colors).rgba

        self._set_uniform(prog, "u_color_a", (ra, ga, ba))
        self._set_uniform(prog, "u_color_b", (rb, gb, bb))
        self._set_uniform(prog, "u_color_c", (rc, gc, bc))
        self._set_uniform(prog, "u_color_d", (rd, gd, bd))

        self._set_uniform(prog, "u_wave_speed", self.wave_speed)
        self._set_uniform(prog, "u_noise_speed", self.noise_speed)
        self._set_uniform(prog, "u_wave_frequency", self.wave_frequency)
        self._set_uniform(prog, "u_wave_amplitude", self.wave_amplitude)
        self._set_uniform(prog, "u_wave_amplitude_y_ratio", self.wave_amplitude_y_ratio)
        self._set_uniform(prog, "u_rotation_spread", self.rotation_spread)
        self._set_uniform(prog, "u_rotation_offset", self.rotation_offset)
        self._set_uniform(prog, "u_angle", self.angle)
        self._set_uniform(prog, "u_opacity", self.opacity)

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
