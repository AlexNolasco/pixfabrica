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
uniform vec3  u_tint_color;
uniform float u_tint_strength;
uniform float u_luma_alpha;
uniform float u_opacity;

out vec4 frag_color;

// Raymarch budget. Trimmed from the original 350: the loop early-exits via the
// d > 10 break and adaptive stepping, so this only bounds worst-case grazing
// rays. The server renders on GPU, so this stays generous but considered.
#define MAX_STEPS 256

void main()
{
    float px = gl_FragCoord.x - u_origin.x;
    float py = (u_canvas_h - gl_FragCoord.y) - u_origin.y;

    if (px < 0.0 || px >= u_res.x || py < 0.0 || py >= u_res.y) discard;

    vec2 C = vec2(px, py);
    vec2 R = u_res;
    vec2 u = (C * 2.0 - R) / R.y;

    float t = u_t;
    float d = fract(sin(dot(C, vec2(12.9898, 78.233))) * 43758.5453) * 0.02;

    vec3 ro = vec3(0.0, 0.0, -1.8);
    vec3 rd = normalize(vec3(u, 1.4 - length(u) * 0.25));
    vec3 co = vec3(0.0);

    // Dual rotation animates the camera through the volume over time.
    mat2 r1 = mat2(cos(t * 0.3), sin(t * 0.3), -sin(t * 0.3), cos(t * 0.3));
    mat2 r2 = mat2(cos(t * 0.2), sin(t * 0.2), -sin(t * 0.2), cos(t * 0.2));
    ro.yz *= r1; rd.yz *= r1;
    ro.xz *= r2; rd.xz *= r2;

    for (int i = 0; i < MAX_STEPS; i++) {
        vec3 p = ro + rd * d;
        float l = length(p);
        if (l < 0.005) { d += 0.005; continue; }

        // Log-polar warp of the sample point feeds a 12-octave fractal density.
        vec3 q = vec3(log(l) - t * 0.75, exp(-p.z / l + 0.5), atan(p.x, p.y));
        float e = q.y - 1.0, s = 2.0;
        for (int j = 0; j < 12; j++) {
            e -= abs(dot(cos(q.zxy * s), vec3(0.2) - sin(q * s))) / s * 0.42;
            s *= 1.95;
        }

        vec3 cb = mix(
            0.5 + 0.5 * cos(vec3(0.0, 0.35, 0.75) * 6.28318 + q.x * 2.5 - q.z * 1.5 + t * 1.5),
            vec3(1.0, 0.3, 0.6),
            sin(l * 8.0 - t * 4.0) * 0.5 + 0.5);
        co += cb * smoothstep(0.04, 0.0, e) * 0.01 * exp(-d * 0.3) + cb * 0.0015 * exp(-d * 0.2);

        d += max(abs(e * l * 0.3), 0.002);
        if (d > 10.0) break;
    }

    // Tone-map, then the vintage post chain: vignette + film grain.
    co = pow(1.0 - exp(-co * 2.5), vec3(0.4545));

    vec2 cu = C / R;
    co *= 0.5 + 0.5 * pow(16.0 * cu.x * cu.y * (1.0 - cu.x) * (1.0 - cu.y), 0.15);
    co += (fract(sin(dot(cu + t * 0.4, vec2(12.9898, 78.233))) * 43758.5453) - 0.5) * 0.025;

    // Classic sepia grade (the original look at tint_strength = 0).
    vec3 sep = clamp(mix(co,
                         vec3(dot(co, vec3(0.393, 0.769, 0.189)),
                              dot(co, vec3(0.349, 0.686, 0.168)),
                              dot(co, vec3(0.272, 0.534, 0.131))),
                         0.95) * 1.1, 0.0, 1.0);

    // Theme-driven recolor: desaturate to luminance, retint with the theme token.
    float luma = dot(co, vec3(0.299, 0.587, 0.114));
    vec3 tinted = clamp(u_tint_color * luma * 1.1, 0.0, 1.0);

    vec3 rgb = mix(sep, tinted, u_tint_strength);

    float out_luma = dot(rgb, vec3(0.299, 0.587, 0.114));
    float alpha = mix(1.0, clamp(out_luma, 0.0, 1.0), u_luma_alpha) * u_opacity;

    frag_color = vec4(rgb * alpha, alpha);
}
"""

_QUAD = np.array([-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0], dtype="f4")


class SepiaNebulaGL(ClipGL):
    """Rotating volumetric fractal nebula with a vintage sepia grade, GPU-only."""

    clip_type: ClassVar[str] = "std-sepia-nebula-gl"
    clip_category: ClassVar[ClipCategory] = ClipCategory.BACKGROUND
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED, ClipTag.GL]

    speed: float = Field(
        default=1.0,
        ge=0.1,
        le=3.0,
        multiple_of=0.1,
        description="Animation speed multiplier (rotation + nebula evolution)",
    )
    tint_color: ColorToken | Color = color_field(ColorToken.PRIMARY)
    tint_strength: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Theme recolor amount (0 = classic sepia, 1 = fully theme-tinted monochrome)",
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
        self._set_uniform(prog, "u_t", ctx.time.t * self.speed)
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
