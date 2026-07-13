from __future__ import annotations

import math
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

uniform vec3  u_color_bg;
uniform vec3  u_color_hex;

uniform float u_scroll_speed;
uniform float u_scroll_dir;
uniform float u_zoom;
uniform float u_hex_height;
uniform float u_bevel_size;
uniform float u_shadow_strength;
uniform float u_fog_strength;
uniform float u_opacity;

out vec4 frag_color;

#define PI  3.141592654
#define TAU (2.0*PI)
#define ROT(a) mat2(cos(a), sin(a), -sin(a), cos(a))

float sRGB(float t) { return mix(1.055*pow(t, 1.0/2.4) - 0.055, 12.92*t, step(t, 0.0031308)); }
vec3  sRGB(vec3 c)  { return vec3(sRGB(c.x), sRGB(c.y), sRGB(c.z)); }

float tanh_approx(float x) {
  float x2 = x*x;
  return clamp(x*(27.0 + x2)/(27.0+9.0*x2), -1.0, 1.0);
}

float hash(vec2 co) {
  return fract(sin(dot(co.xy, vec2(12.9898,58.233))) * 13758.5453);
}

vec2 hextile(inout vec2 p) {
  const vec2 sz  = vec2(1.0, sqrt(3.0));
  const vec2 hsz = 0.5*sz;
  vec2 p1 = mod(p, sz)-hsz;
  vec2 p2 = mod(p - hsz, sz)-hsz;
  vec2 p3 = dot(p1, p1) < dot(p2, p2) ? p1 : p2;
  vec2 n  = ((p3 - p + hsz)/sz);
  p = p3;
  n -= vec2(0.5);
  return round(n*2.0)*0.5;
}

float hexagon(vec2 p, float r) {
  const vec3 k = vec3(-0.866025404, 0.5, 0.577350269);
  p = abs(p);
  p -= 2.0*min(dot(k.xy, p), 0.0)*k.xy;
  p -= vec2(clamp(p.x, -k.z*r, k.z*r), r);
  return length(p)*sign(p.y);
}

float shape(vec2 p) {
  return hexagon(p.yx, 0.4) - u_bevel_size;
}

float cellHeight(float h) {
  return u_hex_height*(-h);
}

vec3 cell(vec2 p, float h) {
  float hd = shape(p);
  const float he = 0.0075*2.0;
  float hh = -he*smoothstep(he, -he, hd);
  return vec3(hd, hh, cellHeight(h));
}

float height(vec2 p, float h) {
  return cell(p, h).y;
}

vec3 normal(vec2 p, float h) {
  vec2 e = vec2(4.0/u_res.y, 0.0);
  vec3 n;
  n.x = height(p + e.xy, h) - height(p - e.xy, h);
  n.y = height(p + e.yx, h) - height(p - e.yx, h);
  n.z = 2.0*e.x;
  return normalize(n);
}

vec3 planeColor(vec3 lp, vec3 pp, vec3 pnor, vec3 bcol, vec3 pcol) {
  vec3  ld  = normalize(lp-pp);
  float dif = pow(max(dot(ld, pnor), 0.0), 1.0);
  return mix(bcol, pcol, dif);
}

const mat2 rots[6] = mat2[](
  ROT(0.0*TAU/6.0),
  ROT(1.0*TAU/6.0),
  ROT(2.0*TAU/6.0),
  ROT(3.0*TAU/6.0),
  ROT(4.0*TAU/6.0),
  ROT(5.0*TAU/6.0)
);

const vec2 base_off = vec2(1.0, 0.0);

const vec2 offs[6] = vec2[](
  base_off*rots[0],
  base_off*rots[1],
  base_off*rots[2],
  base_off*rots[3],
  base_off*rots[4],
  base_off*rots[5]
);

float cutSlice(vec2 p, vec2 o) {
  p.x = abs(p.x);
  o.x *= 0.5;
  vec2 nn = normalize(vec2(o));
  vec2 n  = vec2(nn.y, -nn.x);
  float d0 = length(p-o);
  float d1 = -(p.y-o.y);
  float d2 = dot(n, p);
  bool b = p.x > o.x && (dot(nn, p)-dot(nn, o)) < 0.0;
  return b ? d0 : max(d1, d2);
}

float hexSlice(vec2 p, int n) {
  n = (6-n)%6;
  p *= rots[n];
  p = p.yx;
  const vec2 dim = vec2(0.5*2.0/sqrt(3.0), 0.5);
  return cutSlice(p, dim);
}

vec3 effect(vec2 p) {
  float aa = 2.0/(u_zoom*u_res.y);

  p = vec2(p.y, p.x);

  vec3 lp = vec3(3.0, 0.0, 1.0);

  p -= vec2(0.195, 0.0);
  p /= u_zoom;

  float toff    = u_scroll_speed * u_t;
  vec2  scroll  = vec2(cos(u_scroll_dir), sin(u_scroll_dir)) * toff;
  p    += scroll;
  lp.xy += scroll;

  vec2  hp = p;
  vec2  hn = hextile(hp);
  float hh = hash(hn);
  vec3  c  = cell(hp, hh);
  float cd = c.x;
  float ch = c.z;

  vec3 fpp = vec3(p, ch);
  vec3 bpp = vec3(p, 0.0);

  vec3  bnor = vec3(0.0, 0.0, 1.0);
  vec3  bdif = lp-bpp;
  float bl2  = dot(bdif, bdif);

  vec3 fnor = normal(hp, hh);
  vec3 fld  = normalize(lp-fpp);

  float sf = 0.0;
  for (int i = 0; i < 6; ++i) {
    vec2  ip  = p + offs[i];
    vec2  ihn = hextile(ip);
    float ihh = hash(ihn);
    float ich = cellHeight(ihh);
    float iii = (ich-ch)/fld.z;
    vec3  ipp = vec3(hp, ch)+iii*fld;
    float hsd = hexSlice(ipp.xy, i);
    if (ich > ch) {
      sf += exp(-u_shadow_strength*tanh_approx(1.0/(10.0*iii))*max(hsd, 0.0));
    }
  }

  vec3 bpcol = planeColor(lp, bpp, bnor, vec3(0.0), u_color_bg);
  vec3 fpcol = planeColor(lp, fpp, fnor, bpcol,     u_color_hex);

  vec3 col = bpcol;
  col = mix(col, fpcol, smoothstep(aa, -aa, cd));
  col *= 1.0-tanh_approx(sf);

  float fo = exp(-u_fog_strength*max(bl2, 0.0));
  col *= fo;
  col  = mix(bpcol, col, fo);

  return col;
}

void main() {
  float px = gl_FragCoord.x - u_origin.x;
  float py = (u_canvas_h - gl_FragCoord.y) - u_origin.y;

  vec2 q = vec2(px, py) / u_res;
  vec2 p = -1.0 + 2.0*q;
  p.x *= u_res.x/u_res.y;

  vec3 col = effect(p);
  col = sRGB(col);

  frag_color = vec4(col * u_opacity, u_opacity);
}
"""

_QUAD = np.array(
    [-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0],
    dtype="f4",
)


class HexBackgroundGL(ClipGL):
    """Infinite scrolling hexagon grid background with faked 3D shadows, fully GPU-driven."""

    clip_type: ClassVar[str] = "std-hex-background-gl"
    clip_category: ClassVar[ClipCategory] = ClipCategory.BACKGROUND
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED, ClipTag.GL]

    color_background: ColorToken | Color = color_field(ColorToken.PRIMARY)
    color_hex: ColorToken | Color = color_field(ColorToken.SECONDARY)

    scroll_speed: float = Field(
        default=0.2, ge=0, le=8.0, multiple_of=0.1, description="Scroll speed multiplier"
    )
    scroll_direction: float = Field(
        default=0.0, ge=0.0, le=360.0, multiple_of=1.0, description="Scroll direction in degrees"
    )
    zoom: float = Field(
        default=0.33,
        ge=0.0,
        multiple_of=0.01,
        description="Zoom factor — lower values give larger hexes",
    )
    hex_height: float = Field(
        default=0.5, ge=0.0, le=1.0, multiple_of=0.1, description="Hex extrusion height (0–1)"
    )
    bevel_size: float = Field(
        default=0.2,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Edge bevel as fraction of hex radius (0–1)",
    )
    shadow_strength: float = Field(
        default=0.5, ge=0.0, le=1.0, multiple_of=0.1, description="Shadow sharpness (0–1)"
    )
    fog_strength: float = Field(
        default=0.2, ge=0.0, le=1.0, multiple_of=0.1, description="Distance fog falloff (0–1)"
    )
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)

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

        rbg, gbg, bbg, _ = resolve_color(self.color_background, ctx.job.colors).rgba
        rhx, ghx, bhx, _ = resolve_color(self.color_hex, ctx.job.colors).rgba

        self._set_uniform(prog, "u_color_bg", (rbg, gbg, bbg))
        self._set_uniform(prog, "u_color_hex", (rhx, ghx, bhx))

        self._set_uniform(prog, "u_scroll_speed", self.scroll_speed)
        self._set_uniform(prog, "u_scroll_dir", math.radians(self.scroll_direction) - math.pi / 2)
        self._set_uniform(prog, "u_zoom", self.zoom)
        self._set_uniform(prog, "u_hex_height", self.hex_height * 0.2)
        self._set_uniform(prog, "u_bevel_size", self.bevel_size * 0.4)
        self._set_uniform(prog, "u_shadow_strength", self.shadow_strength * 40.0)
        self._set_uniform(prog, "u_fog_strength", self.fog_strength * 0.1)
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
