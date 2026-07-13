from __future__ import annotations

from typing import Any, ClassVar, Literal, cast

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

uniform vec3  u_color_fire;
uniform float u_speed;
uniform float u_rotation_speed;
uniform float u_direction;
uniform float u_turbulence;
uniform float u_color_intensity;
uniform float u_luma_alpha;
uniform float u_opacity;

out vec4 frag_color;

void main() {
    float px = gl_FragCoord.x - u_origin.x;
    float py = (u_canvas_h - gl_FragCoord.y) - u_origin.y;

    vec2 uv = (vec2(px, py) - u_res * 0.5) / u_res.y;

    float i = 0.0, d = 0.0, s, n;
    vec3 p;
    vec4 o = vec4(0.0);

    for (; i++ < 100.0; ) {
        p = vec3(uv * d, d + u_t * 4.0 * u_speed);
        p += cos(p.z + u_t + p.yzx * 0.5) * u_turbulence;
        s = 4.0 + sin(u_t * 0.7) * 4.0 - length(p.xy);
        p.yx *= mat2(cos(u_t * u_rotation_speed * u_direction + vec4(0.0, 33.0, 11.0, 0.0)));
        for (n = 0.1; n < 2.0;
            s -= abs(dot(sin(p.z + u_t + p * n * 16.0), vec3(0.07))) / n,
            n += n);
        d += s = 0.01 + abs(s) * 0.1;
        o += vec4(1.0) / s;
    }

    vec4 fire = tanh(vec4(5.0, 2.0, 1.0, 1.0) * o * o / d / (2e6 / u_color_intensity));
    vec3 tinted = fire.rgb * u_color_fire;

    float luma  = dot(tinted, vec3(0.299, 0.587, 0.114));
    float alpha = mix(1.0, clamp(luma, 0.0, 1.0), u_luma_alpha) * u_opacity;

    frag_color = vec4(tinted * alpha, alpha);
}
"""

_QUAD = np.array(
    [-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0],
    dtype="f4",
)


class InfernoTunnelGL(ClipGL):
    """Raymarched fire tunnel — a procedural inferno flythrough, fully GPU-driven."""

    clip_type: ClassVar[str] = "std-inferno-tunnel-gl"
    clip_category: ClassVar[ClipCategory] = ClipCategory.BACKGROUND
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED, ClipTag.GL]

    color_fire: ColorToken | Color = color_field(ColorToken.PRIMARY)

    speed: float = Field(
        default=1.0,
        ge=0.0,
        le=10,
        multiple_of=0.1,
        description="Tunnel fly-through speed (1 = default)",
    )
    rotation_speed: float = Field(
        default=1.0, ge=0, le=10.0, multiple_of=0.1, description="Rotation rate (0 = no rotation)"
    )
    direction: Literal["cw", "ccw"] = Field(default="cw", description="Rotation direction")
    turbulence: float = Field(default=0.6, ge=0.0, description="Warp distortion amplitude")
    color_intensity: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Fire brightness multiplier (1 = default)",
    )
    luma_alpha: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Luma-based transparency (0 = solid, 1 = dark areas transparent)",
    )
    opacity: float = Field(
        default=1.0, ge=0.0, le=1.0, multiple_of=0.1, description="Overall layer opacity"
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

        r, g, b, _ = resolve_color(self.color_fire, ctx.job.colors).rgba
        self._set_uniform(prog, "u_color_fire", (r, g, b))

        self._set_uniform(prog, "u_speed", self.speed)
        self._set_uniform(prog, "u_rotation_speed", self.rotation_speed)
        self._set_uniform(prog, "u_direction", 1.0 if self.direction == "cw" else -1.0)
        self._set_uniform(prog, "u_turbulence", self.turbulence)
        self._set_uniform(prog, "u_color_intensity", self.color_intensity)
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
