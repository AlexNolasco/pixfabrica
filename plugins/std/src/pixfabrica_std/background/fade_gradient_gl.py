from __future__ import annotations

from typing import Any, ClassVar, cast

import moderngl
import numpy as np
from pydantic import Field, PrivateAttr

from pixfabrica_core.clips import ClipCategory, ClipGL, ClipTag, PrepareContext, RenderContext
from pixfabrica_core.graphics import Rect
from pixfabrica_core.theme.color import Color, ColorToken, color_field, resolve_color
from pixfabrica_std.background.gradient import _DIR_POINTS, GradientDirection

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
uniform vec2  u_grad_start;
uniform vec2  u_grad_end;
uniform vec3  u_color;
uniform float u_brightness;
uniform float u_opacity;

out vec4 frag_color;

void main() {
    float px = gl_FragCoord.x - u_origin.x;
    float py = (u_canvas_h - gl_FragCoord.y) - u_origin.y;

    vec2 uv = vec2(px / u_res.x, py / u_res.y);
    vec2 dir = u_grad_end - u_grad_start;
    float denom = dot(dir, dir);
    float t = denom > 1e-6 ? dot(uv - u_grad_start, dir) / denom : 0.0;
    t = clamp(t, 0.0, 1.0);

    float fade = 1.0 - t;
    vec3 rgb = u_color * u_brightness;
    float alpha = fade * u_opacity;
    frag_color = vec4(rgb * alpha, alpha);
}
"""

_QUAD = np.array(
    [-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0],
    dtype="f4",
)


class FadeGradientGL(ClipGL):
    """Single-color linear fade to transparent over the clip bounds."""

    clip_type: ClassVar[str] = "std-fade-gradient-gl"
    clip_category: ClassVar[ClipCategory] = ClipCategory.BACKGROUND
    clip_tags: ClassVar[list[str]] = [ClipTag.GRADIENT, ClipTag.GL]

    color: ColorToken | Color = color_field(ColorToken.BACKGROUND)
    direction: GradientDirection = Field(
        default="to bottom",
        description="Direction the color fades toward transparency",
    )
    brightness: float = Field(
        default=1.0,
        ge=0.2,
        le=3.0,
        multiple_of=0.1,
        description="Color brightness multiplier",
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
        sx, sy, ex, ey = _DIR_POINTS[self.direction]

        self._set_uniform(prog, "u_res", (self._bounds_w, self._bounds_h))
        self._set_uniform(prog, "u_origin", (self._bounds_x, self._bounds_y))
        self._set_uniform(prog, "u_canvas_h", self._canvas_h)
        self._set_uniform(prog, "u_grad_start", (sx, sy))
        self._set_uniform(prog, "u_grad_end", (ex, ey))

        r, g, b, _ = resolve_color(self.color, ctx.job.colors).rgba
        self._set_uniform(prog, "u_color", (r, g, b))
        self._set_uniform(prog, "u_brightness", self.brightness)
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
