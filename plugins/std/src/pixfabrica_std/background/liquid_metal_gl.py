from __future__ import annotations

from typing import Any, ClassVar

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
uniform float u_turbulence;
uniform vec3  u_low_color;
uniform vec3  u_high_color;
uniform float u_luma_alpha;
uniform float u_opacity;

out vec4 frag_color;

void main()
{
    float px = gl_FragCoord.x - u_origin.x;
    float py = (u_canvas_h - gl_FragCoord.y) - u_origin.y;

    if (px < 0.0 || px >= u_res.x || py < 0.0 || py >= u_res.y) discard;

    // Shadertoy-equivalent UV: centered, normalized by the shorter axis.
    vec2 uv = (2.0 * vec2(px, py) - u_res) / min(u_res.x, u_res.y);

    // Domain-warp the UV: each iteration folds the field back on itself,
    // producing the flowing "liquid metal" veins. u_turbulence is the
    // original 0.6 amplitude.
    for (float i = 1.0; i < 10.0; i++) {
        uv.x += u_turbulence / i * cos(i * 2.5 * uv.y + u_t);
        uv.y += u_turbulence / i * cos(i * 1.5 * uv.x + u_t);
    }

    // Bright veins where sin(...) -> 0. Clamp the divisor so the 0.1/|sin|
    // singularity does not blow up to NaN/black artifacts.
    float denom = max(abs(sin(u_t - uv.y - uv.x)), 1e-3);
    float g = clamp(0.1 / denom, 0.0, 1.0);

    // Duotone ramp: dark base -> low color, bright veins -> high color.
    vec3 rgb = mix(u_low_color, u_high_color, g);

    float luma  = dot(rgb, vec3(0.299, 0.587, 0.114));
    float alpha = mix(1.0, clamp(luma, 0.0, 1.0), u_luma_alpha) * u_opacity;

    frag_color = vec4(rgb * alpha, alpha);
}
"""

_QUAD = np.array([-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0], dtype="f4")


class LiquidMetalGL(ClipGL):
    """Flowing liquid-metal background — domain-warped veins tinted by theme colors."""

    clip_type: ClassVar[str] = "std-liquid-metal-gl"
    clip_category: ClassVar[ClipCategory] = ClipCategory.BACKGROUND
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED, ClipTag.GL]

    speed: float = Field(
        default=1.0,
        ge=0.1,
        le=3.0,
        multiple_of=0.1,
        description="Animation speed multiplier",
    )
    turbulence: float = Field(
        default=0.6,
        ge=0.0,
        le=1.5,
        multiple_of=0.1,
        description="How hard the metal churns — distortion amplitude per warp iteration",
    )
    low_color: ColorToken | Color = color_field(ColorToken.BACKGROUND)
    high_color: ColorToken | Color = color_field(ColorToken.PRIMARY)
    luma_alpha: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Dark-area transparency (0 = always opaque background, 1 = dark areas fully transparent)",
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
        if name in prog:
            member = prog[name]
            if isinstance(member, moderngl.Uniform):
                member.value = value

    def draw(self, ctx: RenderContext) -> None:
        gl: moderngl.Context = ctx.canvas

        if self._program is None:
            self._program = gl.program(vertex_shader=_VERT, fragment_shader=_FRAG)
            vbo = gl.buffer(_QUAD.tobytes())
            self._vao = gl.simple_vertex_array(self._program, vbo, "in_vert")

        prog = self._program
        lr, lg, lb, _ = resolve_color(self.low_color, ctx.job.colors).rgba
        hr, hg, hb, _ = resolve_color(self.high_color, ctx.job.colors).rgba

        self._set_uniform(prog, "u_res", (self._bounds_w, self._bounds_h))
        self._set_uniform(prog, "u_origin", (self._bounds_x, self._bounds_y))
        self._set_uniform(prog, "u_canvas_h", self._canvas_h)
        self._set_uniform(prog, "u_t", ctx.time.t * self.speed)
        self._set_uniform(prog, "u_turbulence", self.turbulence)
        self._set_uniform(prog, "u_low_color", (lr, lg, lb))
        self._set_uniform(prog, "u_high_color", (hr, hg, hb))
        self._set_uniform(prog, "u_luma_alpha", self.luma_alpha)
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
