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
uniform vec3  u_color_glow_top;
uniform vec3  u_color_glow_bottom;

uniform float u_speed_x;
uniform float u_speed_y;
uniform float u_zoom;
uniform float u_scroll_speed;
uniform float u_fire_sharpness;
uniform float u_glow_amount;
uniform float u_flip_y;
uniform float u_luma_alpha;
uniform float u_opacity;

out vec4 frag_color;

float rand(vec2 n) {
  return fract(sin(cos(dot(n, vec2(12.9898, 12.1414)))) * 83758.5453);
}

float noise(vec2 n) {
  const vec2 d = vec2(0.0, 1.0);
  vec2 b = floor(n), f = smoothstep(vec2(0.0), vec2(1.0), fract(n));
  return mix(
    mix(rand(b),        rand(b + d.yx), f.x),
    mix(rand(b + d.xy), rand(b + d.yy), f.x),
    f.y
  );
}

float fbm(vec2 n) {
  float total = 0.0, amplitude = 1.0;
  for (int i = 0; i < 5; i++) {
    total     += noise(n) * amplitude;
    n         += n * 1.7;
    amplitude *= 0.47;
  }
  return total;
}

void main() {
  float px = gl_FragCoord.x - u_origin.x;
  float py = (u_canvas_h - gl_FragCoord.y) - u_origin.y;

  vec2 uv = vec2(px, py) / u_res;
  float eff_py  = mix(py, u_res.y - py, u_flip_y);
  float eff_uvy = mix(uv.y, 1.0 - uv.y, u_flip_y);
  float dist = u_zoom - sin(u_t * 0.4) / 1.89;

  vec2 p = vec2(px, py) * dist / u_res.xx;
  p += sin(p.yx * 4.0 + vec2( 0.2, -0.3) * u_t) * 0.04;
  p += sin(p.yx * 8.0 + vec2( 0.6,  0.1) * u_t) * 0.01;
  p.x -= u_t * u_scroll_speed;

  float q  = fbm(p - u_t * 0.30 + 1.0 * sin(u_t + 0.5) / 2.0);
  float qb = fbm(p - u_t * 0.40 + 0.1 * cos(u_t)       / 2.0);
  float q2 = fbm(p - u_t * 0.44 - 5.0 * cos(u_t)       / 2.0)  - 6.0;
  float q3 = fbm(p - u_t * 0.90 - 10.0 * cos(u_t)      / 15.0) - 4.0;
  float q4 = fbm(p - u_t * 1.40 - 20.0 * sin(u_t)      / 14.0) + 2.0;
  q = (q + qb - 0.4 * q2 - 2.0 * q3 + 0.6 * q4) / 3.8;

  vec2 r = vec2(
    fbm(p + q / 2.0 + u_t * u_speed_x - p.x - p.y),
    fbm(p + q       - u_t * u_speed_y)
  );

  float fire_y = eff_py * dist / u_res.x;
  vec3 color = u_color_fire / pow((r.y + r.y) * max(0.0, fire_y) + 0.1, u_fire_sharpness);

  float tex = fbm(p * 0.6 + vec2(0.5, 0.1));
  color += (tex * 0.01 * pow((r.y + r.y) * 0.65, 5.0) + u_glow_amount)
         * mix(u_color_glow_top, u_color_glow_bottom, clamp(eff_uvy - r.x * 0.1, 0.0, 1.0));

  color = color / (1.0 + max(vec3(0.0), color));

  float luma  = dot(color, vec3(0.299, 0.587, 0.114));
  float alpha = mix(1.0, clamp(luma, 0.0, 1.0), u_luma_alpha) * u_opacity;
  frag_color = vec4(color * alpha, alpha);
}
"""

_QUAD = np.array(
    [-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0],
    dtype="f4",
)


class FireBaseGL(ClipGL):
    """Turbulent fire background using layered FBM domain warping, fully GPU-driven."""

    clip_type: ClassVar[str] = "std-fire-base-gl"
    clip_category: ClassVar[ClipCategory] = ClipCategory.BACKGROUND
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED, ClipTag.GL]
    clip_presets: ClassVar[list[ClipPreset]] = [
        ClipPreset(
            id="campfire",
            label="Campfire",
            values={
                "speed_x": -1.0,
                "speed_y": -1.0,
                "zoom": 3.0,
                "scroll_speed": 0.2,
                "fire_sharpness": 5.0,
                "glow_amount": 0.03,
                "flip_vertical": True,
                "luma_alpha": 1.0,
                "opacity": 1.0,
            },
        ),
        ClipPreset(
            id="inferno",
            label="Inferno",
            values={
                "speed_x": -4.0,
                "speed_y": -4.0,
                "zoom": 4.5,
                "scroll_speed": 1.1,
                "fire_sharpness": 2.6,
                "glow_amount": 0.1,
                "flip_vertical": True,
                "luma_alpha": 0.6,
                "opacity": 1.0,
            },
        ),
        ClipPreset(
            id="ember_glow",
            label="Ember Glow",
            values={
                "speed_x": -1.0,
                "speed_y": -1.0,
                "zoom": 3.0,
                "scroll_speed": 0.1,
                "fire_sharpness": 3.0,
                "glow_amount": 0.15,
                "flip_vertical": True,
                "luma_alpha": 0.8,
                "opacity": 1.0,
            },
        ),
        ClipPreset(
            id="torch",
            label="Torch",
            values={
                "speed_x": -0.5,
                "speed_y": -3.0,
                "zoom": 2.5,
                "scroll_speed": 0.3,
                "fire_sharpness": 6.0,
                "glow_amount": 0.04,
                "flip_vertical": True,
                "luma_alpha": 1.0,
                "opacity": 1.0,
            },
        ),
        ClipPreset(
            id="hellfire",
            label="Hellfire",
            values={
                "speed_x": -3.0,
                "speed_y": -2.0,
                "zoom": 4.0,
                "scroll_speed": 0.6,
                "fire_sharpness": 3.5,
                "glow_amount": 0.12,
                "flip_vertical": False,
                "luma_alpha": 0.0,
                "opacity": 1.0,
            },
        ),
    ]

    color_fire: ColorToken | Color = color_field(ColorToken.PRIMARY)
    color_glow_top: ColorToken | Color = color_field(ColorToken.SECONDARY)
    color_glow_bottom: ColorToken | Color = color_field(ColorToken.ACCENT)

    speed_x: float = Field(
        default=-2.0, ge=-5.0, le=5.0, multiple_of=0.1, description="Turbulence X layer speed"
    )
    speed_y: float = Field(
        default=-2.0, ge=-5.0, le=5.0, multiple_of=0.1, description="Turbulence Y layer speed"
    )
    zoom: float = Field(
        default=3.5, ge=2.1, le=5.0, multiple_of=0.1, description="Zoom factor (base dist)"
    )
    scroll_speed: float = Field(
        default=0.9,
        ge=0.0,
        le=2.0,
        multiple_of=0.1,
        description="Horizontal scroll speed multiplier",
    )
    fire_sharpness: float = Field(
        default=4.0,
        ge=1.1,
        multiple_of=0.1,
        le=10.0,
        description="Flame peak sharpness (pow exponent)",
    )
    glow_amount: float = Field(
        default=0.055, ge=0.0, le=1.0, multiple_of=0.01, description="Ambient glow floor"
    )
    flip_vertical: bool = Field(
        default=True, description="Fire rises from bottom (True) or top (False)"
    )
    luma_alpha: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Luma-based transparency (0 = solid, 1 = dark areas transparent)",
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

        self._set_uniform(prog, "u_res", (self._bounds_w, self._bounds_h))
        self._set_uniform(prog, "u_origin", (self._bounds_x, self._bounds_y))
        self._set_uniform(prog, "u_canvas_h", self._canvas_h)
        self._set_uniform(prog, "u_t", ctx.time.t)

        rf, gf, bf, _ = resolve_color(self.color_fire, ctx.job.colors).rgba
        rt, gt, bt, _ = resolve_color(self.color_glow_top, ctx.job.colors).rgba
        rb, gb, bb, _ = resolve_color(self.color_glow_bottom, ctx.job.colors).rgba

        self._set_uniform(prog, "u_color_fire", (rf, gf, bf))
        self._set_uniform(prog, "u_color_glow_top", (rt, gt, bt))
        self._set_uniform(prog, "u_color_glow_bottom", (rb, gb, bb))

        self._set_uniform(prog, "u_speed_x", self.speed_x)
        self._set_uniform(prog, "u_speed_y", self.speed_y)
        self._set_uniform(prog, "u_zoom", self.zoom)
        self._set_uniform(prog, "u_scroll_speed", self.scroll_speed)
        self._set_uniform(prog, "u_fire_sharpness", self.fire_sharpness)
        self._set_uniform(prog, "u_glow_amount", self.glow_amount)
        self._set_uniform(prog, "u_flip_y", 1.0 if self.flip_vertical else 0.0)
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
