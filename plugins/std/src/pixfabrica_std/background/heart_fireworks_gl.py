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
uniform float u_star_count;
uniform float u_hue_shift;
uniform float u_offset_y;
uniform float u_angle;
uniform float u_luma_alpha;
uniform float u_opacity;

out vec4 frag_color;

#define TWO_PI 6.283185307179586

float star5SDF(vec2 p, float r, float m) {
    const vec2 k1 = vec2(0.809016994375, -0.587785252292);
    const vec2 k2 = vec2(-k1.x, k1.y);
    p.x = abs(p.x);
    p -= 2.0 * max(dot(k1, p), 0.0) * k1;
    p -= 2.0 * max(dot(k2, p), 0.0) * k2;
    p.x = abs(p.x);
    p.y -= r;
    vec2 ab = m * vec2(-k1.y, k1.x) - vec2(0.0, r);
    float h = clamp(dot(p, ab) / dot(ab, ab), 0.0, 1.0);
    return length(p - ab * h) * sign(p.y * ab.x - p.x * ab.y);
}

float hash1(float p) {
    p = fract(p * .1031 * 9811.164);
    p *= p + 33.33;
    p *= p + p;
    return fract(p);
}

vec2 hash21(float p) {
    vec3 p3 = fract(vec3(p) * vec3(.1031, .1030, .0973) * 1023.468);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.xx + p3.yz) * p3.zy);
}

vec3 colorRibbon(float t) {
    return abs(mod(vec3(0., 1., 2.) / 3. + t + u_hue_shift, 1.) - .5) * 4. - 0.5;
}

vec2 getHeartPosition(float t) {
    return vec2(
        16.0 * sin(t) * sin(t) * sin(t),
        -(13.0 * cos(t) - 5.0 * cos(2.0 * t) - 2.0 * cos(3.0 * t) - cos(4.0 * t))
    );
}

void main() {
    float px = gl_FragCoord.x - u_origin.x;
    float py = (u_canvas_h - gl_FragCoord.y) - u_origin.y;

    if (px < 0.0 || px >= u_res.x || py < 0.0 || py >= u_res.y) discard;

    vec2 uv = (vec2(px, py) * 2.0 - u_res) / u_res.y;
    uv.y = -uv.y;

    uv.y -= (0.5 - u_offset_y) * 2.0;

    float a = radians(-u_angle);
    uv = mat2(cos(a), -sin(a), sin(a), cos(a)) * uv;

    float t      = u_t * 0.5 * u_speed;
    float aspect = u_res.x / u_res.y;
    vec3 color   = vec3(0.0);

    for (float j = 0.0; j < 10.0; j++) {
        float ja = j / 10.0;
        t -= hash1(ja * 33.669);
        float t1  = floor(t);
        float t1f = fract(t);
        float t2fa = min(0.3, t1f) / 0.3;
        float t2fb = max(t1f * step(0.3, t1f) - 0.3, 0.0) / 0.7;
        float flasht = t2fb * (step(0.1, t2fb) - step(0.0, t2fb)) * 10.0;
        vec2 layer1_pos = hash21(t1 * j);
        vec3 col = colorRibbon(hash1(layer1_pos.y));

        for (float i = 0.0; i < u_star_count; i++) {
            float ia = i / u_star_count;
            vec2 layer2_pos = getHeartPosition(ia * TWO_PI) * t2fb * -0.028;
            layer2_pos -= vec2(
                (1.0 - layer1_pos.x * 2.0) * aspect,
                1.0 - max(layer1_pos.y + 0.75, 0.75) * t2fa
            );
            float blink = step(1.0, mod(i, 2.0));
            float sdf   = star5SDF(uv - layer2_pos, 0.05, 0.09) + 0.05;
            color += col * smoothstep(-0.016, flasht * 3.6 + 4.5 + sin(t2fb * 30.0) * blink, 0.02 / sdf);
        }
    }

    vec3 tinted = color * u_color_primary;

    float luma  = dot(tinted, vec3(0.299, 0.587, 0.114));
    float alpha = mix(1.0, clamp(luma, 0.0, 1.0), u_luma_alpha) * u_opacity;
    frag_color = vec4(tinted * alpha, alpha);
}
"""

_QUAD = np.array(
    [-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0],
    dtype="f4",
)


class HeartFireworksGL(ClipGL):
    """Heart-shaped fireworks bursts — 5-pointed star particles exploding along a parametric heart curve."""

    clip_type: ClassVar[str] = "std-heart-fireworks-gl"
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
        default=1.0, ge=0.0, le=3.0, multiple_of=0.1, description="Animation speed (1 = default)"
    )
    star_count: int = Field(
        default=20, ge=5, le=32, multiple_of=1.0, description="Stars per burst (5–40)"
    )
    hue_shift: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Color cycle offset (0–1 = full cycle)",
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
        self._set_uniform(prog, "u_star_count", float(self.star_count))
        self._set_uniform(prog, "u_hue_shift", self.hue_shift)
        self._set_uniform(prog, "u_offset_y", self.offset_y)
        self._set_uniform(prog, "u_angle", self.angle)
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
