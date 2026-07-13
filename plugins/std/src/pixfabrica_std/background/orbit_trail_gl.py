from __future__ import annotations

from typing import Any, ClassVar, cast

import moderngl
import numpy as np
from pydantic import Field, PrivateAttr

from pixfabrica_core.clips import ClipCategory, ClipGL, ClipTag, PrepareContext, RenderContext
from pixfabrica_core.graphics import Rect
from pixfabrica_core.theme.color import Color, ColorToken, color_field, resolve_color
from pixfabrica_std.tilt import ANGLE_FULL_DESC, ANGLE_FULL_MAX, ANGLE_FULL_MIN

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

uniform vec3  u_color_primary;
uniform float u_speed;
uniform float u_hue_shift;
uniform float u_offset_y;
uniform float u_angle;
uniform float u_dot_size;
uniform float u_trail_length;
uniform float u_luma_alpha;
uniform float u_opacity;

out vec4 frag_color;

vec4 hue(float v) {
    return 0.6 + 0.6 * cos(6.3 * v + vec4(0.0, 23.0, 21.0, 0.0));
}

void main() {
    float px = gl_FragCoord.x - u_origin.x;
    float py = (u_canvas_h - gl_FragCoord.y) - u_origin.y;

    if (px < 0.0 || px >= u_res.x || py < 0.0 || py >= u_res.y) discard;

    vec2 uv = (vec2(px, py) * 2.0 - u_res) / u_res.y;

    uv.y += (0.5 - u_offset_y) * 2.0;

    float a = radians(u_angle);
    uv = mat2(cos(a), -sin(a), sin(a), cos(a)) * uv;

    float t     = u_t * 5.0 * u_speed;
    float max_i = 30.0 * u_trail_length;
    vec4  o     = vec4(0.0);

    float aspect = u_res.x / u_res.y;

    for (float i = 0.0; i < min(t, max_i); i += 0.5) {
        float tt = t + sqrt(100.0 - i) * 2.0;
        vec2  m  = vec2(cos(tt) * aspect, sin(2.0 * tt) / 3.5);
        float d  = smoothstep(u_dot_size - i * 0.005, 0.0, length(uv + m));
        o += d * hue(-tt * 0.33 + u_hue_shift) * (1.0 - i * 0.03);
    }

    vec4 col = tanh(o);
    col.rgb *= u_color_primary;

    float luma  = dot(col.rgb, vec3(0.299, 0.587, 0.114));
    float alpha = mix(1.0, clamp(luma, 0.0, 1.0), u_luma_alpha) * u_opacity;
    frag_color = vec4(col.rgb * alpha, alpha);
}
"""

_QUAD = np.array(
    [-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0],
    dtype="f4",
)


class OrbitTrailGL(ClipGL):
    """Lissajous figure-8 comet trail — glowing rainbow dots orbiting a parametric path."""

    clip_type: ClassVar[str] = "std-orbit-trail-gl"
    clip_category: ClassVar[ClipCategory] = ClipCategory.BACKGROUND
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED, ClipTag.GL]

    color_primary: ColorToken | Color = color_field(ColorToken.PRIMARY)

    offset_y: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Vertical position (0 = top, 0.5 = center, 1 = bottom)",
    )
    angle: float = Field(
        default=0.0,
        ge=ANGLE_FULL_MIN,
        le=ANGLE_FULL_MAX,
        multiple_of=1.0,
        description=ANGLE_FULL_DESC,
    )
    opacity: float = Field(
        default=1.0, ge=0.0, le=1.0, multiple_of=0.1, description="Overall layer opacity"
    )
    speed: float = Field(
        default=1.0, ge=0.0, lt=2.0, multiple_of=0.1, description="Animation speed (1 = default)"
    )
    hue_shift: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Color cycle offset (0–1 = full cycle)",
    )
    dot_size: float = Field(
        default=0.2,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Dot radius as a fraction of canvas height",
    )
    trail_length: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Trail length (0 = no trail, 1 = full)",
    )
    luma_alpha: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Luma-based transparency (0 = solid, 1 = dark areas transparent)",
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

        r, g, b, _ = resolve_color(self.color_primary, ctx.job.colors).rgba
        self._set_uniform(prog, "u_color_primary", (r, g, b))

        self._set_uniform(prog, "u_speed", self.speed)
        self._set_uniform(prog, "u_hue_shift", self.hue_shift)
        self._set_uniform(prog, "u_offset_y", self.offset_y)
        self._set_uniform(prog, "u_angle", self.angle)
        self._set_uniform(prog, "u_dot_size", self.dot_size)
        self._set_uniform(prog, "u_trail_length", self.trail_length)
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
