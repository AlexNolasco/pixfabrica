"""Falling snow overlay — transparent GL layer for compositing over backgrounds."""

from __future__ import annotations

from typing import Any, ClassVar, cast

import moderngl
import numpy as np
from pydantic import Field, PrivateAttr

from pixfabrica_core.clips import ClipCategory, ClipGL, ClipTag, PrepareContext, RenderContext
from pixfabrica_core.graphics import Rect
from pixfabrica_core.theme.color import Color, ColorToken, color_field, resolve_color

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
uniform float u_speed;
uniform vec3  u_color;
uniform vec3  u_atmosphere;
uniform float u_atmosphere_strength;
uniform float u_luma_alpha;
uniform float u_opacity;

out vec4 frag_color;

void main() {
    float px = gl_FragCoord.x - u_origin.x;
    float py = (u_canvas_h - gl_FragCoord.y) - u_origin.y;

    if (px < 0.0 || px >= u_res.x || py < 0.0 || py >= u_res.y) discard;

    // Shadertoy fragCoord: origin bottom-left, Y up.
    vec2 shCoord = vec2(px, u_res.y - py);
    float iTime = u_t * u_speed;

    float snow = 0.0;
    float gradient = (1.0 - shCoord.y / u_res.x) * 0.4;
    float random = fract(sin(dot(shCoord, vec2(12.9898, 78.233))) * 43758.5453);

    for (int k = 0; k < 6; k++) {
        for (int i = 0; i < 12; i++) {
            float fi = max(float(i), 1.0);
            float cellSize = 2.0 + float(i) * 3.0;
            float downSpeed = 0.3 + (sin(iTime * 0.4 + float(k + i * 20)) + 1.0) * 0.00008;
            vec2 uv = (shCoord / u_res.x)
                + vec2(
                    0.01 * sin((iTime + float(k * 6185)) * 0.6 + float(i)) * (5.0 / fi),
                    downSpeed * (iTime + float(k * 1352)) * (1.0 / fi)
                );
            vec2 uvStep = ceil(uv * cellSize - vec2(0.5, 0.5)) / cellSize;
            float x = fract(
                sin(dot(uvStep.xy, vec2(12.9898 + float(k) * 12.0, 78.233 + float(k) * 315.156)))
                * 43758.5453 + float(k) * 12.0
            ) - 0.5;
            float y = fract(
                sin(dot(uvStep.xy, vec2(62.2364 + float(k) * 23.0, 94.674 + float(k) * 95.0)))
                * 62159.8432 + float(k) * 12.0
            ) - 0.5;

            float randomMagnitude1 = sin(iTime * 2.5) * 0.7 / cellSize;
            float randomMagnitude2 = cos(iTime * 2.5) * 0.7 / cellSize;

            float d = 5.0 * distance(
                uvStep.xy + vec2(x * sin(y), y) * randomMagnitude1 + vec2(y, x) * randomMagnitude2,
                uv.xy
            );

            float omiVal = fract(sin(dot(uvStep.xy, vec2(32.4691, 94.615))) * 31572.1684);
            if (omiVal < 0.08) {
                float newd = (x + 1.0) * 0.4
                    * clamp(1.9 - d * (15.0 + x * 6.3) * (cellSize / 1.4), 0.0, 1.0);
                snow += newd;
            }
        }
    }

    // Original: vec4(snow) + gradient * vec4(0.4, 0.8, 1.0, 0.0) + random * 0.01
    // Straight-alpha output (GL track blend mode). Snow accumulates well below 1.0 so
    // boost coverage for overlay visibility without washing empty pixels.
    const float FLAKE_GAIN = 2.5;

    vec3 col = vec3(snow) * u_color
        + gradient * u_atmosphere * u_atmosphere_strength
        + random * 0.01;
    float coverage = clamp(snow * FLAKE_GAIN + random * 0.01, 0.0, 1.0);
    float alpha = mix(1.0, coverage, u_luma_alpha) * u_opacity;
    frag_color = vec4(col * alpha, alpha);
}
"""

_QUAD = np.array(
    [-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0],
    dtype="f4",
)


class SnowGL(ClipGL):
    """Animated snowfall overlay — transparent except where flakes and haze appear.

    Drop on a GL track above a background. Dark / empty regions stay transparent so
    layers below remain visible.
    """

    clip_type: ClassVar[str] = "std-snow-gl"
    clip_category: ClassVar[ClipCategory] = ClipCategory.PARTICLES
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED, ClipTag.LOOP, ClipTag.GL, ClipTag.PARTICLE]

    color: ColorToken | Color = color_field(ColorToken.NEUTRAL)
    atmosphere: ColorToken | Color = color_field(
        ColorToken.SECONDARY,
        description="Top-of-frame cool haze tint",
    )
    speed: float = Field(
        default=1.0,
        ge=0.1,
        le=5.0,
        multiple_of=0.1,
        description="Snow drift animation speed",
    )
    atmosphere_strength: float = Field(
        default=0.4,
        ge=0.0,
        le=2.0,
        multiple_of=0.1,
        description="Cool haze tint (strongest toward the bottom of the frame)",
    )
    luma_alpha: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Luma-based transparency (1 = flakes only, 0 = solid fill)",
    )
    opacity: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Overall layer opacity",
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
        snow_r, snow_g, snow_b, _ = resolve_color(self.color, ctx.job.colors).rgba
        atm_r, atm_g, atm_b, _ = resolve_color(self.atmosphere, ctx.job.colors).rgba

        self._set_uniform(prog, "u_res", (self._bounds_w, self._bounds_h))
        self._set_uniform(prog, "u_origin", (self._bounds_x, self._bounds_y))
        self._set_uniform(prog, "u_canvas_h", self._canvas_h)
        self._set_uniform(prog, "u_t", ctx.time.t)
        self._set_uniform(prog, "u_speed", self.speed)
        self._set_uniform(prog, "u_color", (snow_r, snow_g, snow_b))
        self._set_uniform(prog, "u_atmosphere", (atm_r, atm_g, atm_b))
        self._set_uniform(prog, "u_atmosphere_strength", self.atmosphere_strength)
        self._set_uniform(prog, "u_luma_alpha", self.luma_alpha)
        self._set_uniform(prog, "u_opacity", self.opacity)

        gl.scissor = (
            int(self._bounds_x),
            int(ctx.job.height - self._bounds_y - ctx.bounds.height),
            int(self._bounds_w),
            int(self._bounds_h),
        )

        assert self._vao is not None
        self._vao.render(moderngl.TRIANGLES)

        gl.scissor = None
