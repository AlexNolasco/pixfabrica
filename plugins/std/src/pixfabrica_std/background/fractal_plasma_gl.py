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
uniform float u_speed;
uniform float u_phase_offset;
uniform vec3  u_tint_color;
uniform float u_tint_strength;
uniform float u_luma_alpha;
uniform float u_opacity;

out vec4 frag_color;

// Safe tanh — clamps argument to avoid black NaN artifacts on extreme values.
// See https://www.shadertoy.com/view/4sc3z2
vec2 stanh(vec2 a) {
    return tanh(clamp(a, -40.0, 40.0));
}

void main()
{
    float px = gl_FragCoord.x - u_origin.x;
    float py = (u_canvas_h - gl_FragCoord.y) - u_origin.y;

    if (px < 0.0 || px >= u_res.x || py < 0.0 || py >= u_res.y) discard;

    // Shadertoy-equivalent UV: centered, Y-up, normalized by height
    vec2 u = .2 * (vec2(px, py) * 2.0 - u_res) / u_res.y;
    vec2 v;

    // z encodes RGB phase offsets; the 1-2-3 radian spacing creates the color palette.
    // phase_offset shifts the base hue while preserving relative channel spacing.
    vec4 z = vec4(1.0 + u_phase_offset, 2.0 + u_phase_offset, 3.0 + u_phase_offset, 0.0);
    vec4 o = z;

    // Original: https://www.shadertoy.com/view/wlfXzn — golf shader by Nguyen2007
    // t advances by 1 each iteration (++t in body) so each layer sees a different time.
    for (float a = .5, t = u_t * u_speed, i = 0.0;
         ++i < 19.;
         o += (1. + cos(z + t))
            / length((1. + i * dot(v, v))
                   * sin(1.5 * u / (.5 - dot(u, u)) - 9. * u.yx + t))
         )
        v = cos(++t - 7. * u * pow(a += .03, i)) - 5. * u,
        u += stanh(40. * dot(u *= mat2(cos(i + .02 * t - z.wxzw * 11.)), u)
                       * cos(1e2 * u.yx + t)) / 2e2
           + .2 * a * u
           + cos(4. / exp(dot(o, o) / 1e2) + t) / 3e2;

    // HDR tone-map: brings accumulated o into a perceptually nice range
    o = 25.6 / (min(o, 13.) + 164. / o) - dot(u, u) / 250.;

    vec3 rgb = clamp(o.rgb, 0.0, 1.0);
    rgb = mix(rgb, rgb * u_tint_color, u_tint_strength);

    float luma  = dot(rgb, vec3(0.299, 0.587, 0.114));
    float alpha = mix(1.0, clamp(luma, 0.0, 1.0), u_luma_alpha) * u_opacity;

    frag_color = vec4(rgb * alpha, alpha);
}
"""

_QUAD = np.array([-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0], dtype="f4")


class FractalPlasmaGL(ClipGL):
    """19-iteration fractal plasma accumulator — psychedelic color-cycling fill, GPU-only."""

    clip_type: ClassVar[str] = "std-fractal-plasma-gl"
    clip_category: ClassVar[ClipCategory] = ClipCategory.BACKGROUND
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED, ClipTag.GL]

    speed: float = Field(
        default=1.0,
        ge=0.1,
        le=3.0,
        multiple_of=0.1,
        description="Animation speed multiplier",
    )
    phase_offset: float = Field(
        default=0.0,
        ge=0.0,
        le=6.3,
        multiple_of=0.1,
        description="Color phase shift — rotates the starting hue (0–6.3 ≈ one full cycle)",
    )
    tint_color: ColorToken | Color = color_field(ColorToken.PRIMARY)
    tint_strength: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="How strongly the tint color multiplies the fractal palette (0 = off, 1 = full tint)",
    )
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
        r, g, b, _ = resolve_color(self.tint_color, ctx.job.colors).rgba

        self._set_uniform(prog, "u_res", (self._bounds_w, self._bounds_h))
        self._set_uniform(prog, "u_origin", (self._bounds_x, self._bounds_y))
        self._set_uniform(prog, "u_canvas_h", self._canvas_h)
        self._set_uniform(prog, "u_t", ctx.time.t)
        self._set_uniform(prog, "u_speed", self.speed)
        self._set_uniform(prog, "u_phase_offset", self.phase_offset)
        self._set_uniform(prog, "u_tint_color", (r, g, b))
        self._set_uniform(prog, "u_tint_strength", self.tint_strength)
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
