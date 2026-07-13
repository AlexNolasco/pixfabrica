"""Rainy-window post-process — Heartfelt-style procedural rain.

Adapted from Martijn Steinrucken's "Heartfelt" (Shadertoy ltffzl, CC BY-NC-SA 3.0).
The drop / trail mask is a pure function of (uv, t); surface normals come from finite
differences on that mask; refraction is a single sharp re-sample of the composited
scene; the frosted glass uses cheap mipmap LOD instead of the original 32×8 Gaussian.

Stateless ``draw()`` — safe for multi-process rendering. No ``prepare()`` work.
"""

from __future__ import annotations

from typing import Any, ClassVar

import moderngl
import numpy as np
from pydantic import Field, PrivateAttr

from pixfabrica_core.clips import (
    ClipCategory,
    ClipTag,
    GLPostProcessClip,
    PrepareContext,
    RenderContext,
)
from pixfabrica_core.graphics import Rect
from pixfabrica_core.theme.color import Color, ColorToken, color_field, resolve_color

_VERT = """
#version 330 core
in vec2 in_vert;
out vec2 v_uv;
void main() {
    v_uv = in_vert * 0.5 + 0.5;
    gl_Position = vec4(in_vert, 0.0, 1.0);
}
"""

# Heartfelt's Rain() / Drops() / StaticDrops(), rewritten with parameterised drop
# size, grid layout, sheets, and rain amount.  All hashes (N13, N) preserved.
_FRAG = """
#version 330 core

uniform sampler2D u_source;        // mipmapped composited scene
uniform vec2      u_resolution;    // job width, height (pixels)
uniform float     u_t;             // seconds
uniform float     u_drop_size;     // ~0.05–0.30, default 0.20 in original
uniform float     u_rain_amount;   // 0..1 — how many sheets of large drops contribute
uniform vec2      u_drop_grid;     // columns, rows (default 6, 1)
uniform float     u_blur_lod;      // mipmap LOD for the frosted glass (replaces 256-tap blur)
uniform float     u_refraction;    // strength of normal-driven UV offset
uniform float     u_glass_opacity; // ambient tint over blurred glass
uniform vec3      u_glass_tint;
uniform float     u_zoom;          // background zoom (UV recentering, default 0.9)

in  vec2 v_uv;
out vec4 fragColor;

#define S(a, b, t) smoothstep(a, b, t)

vec3 N13(float p) {
    vec3 p3 = fract(vec3(p) * vec3(0.1031, 0.11369, 0.13787));
    p3 += dot(p3, p3.yzx + 19.19);
    return fract(vec3(
        (p3.x + p3.y) * p3.z,
        (p3.x + p3.z) * p3.y,
        (p3.y + p3.z) * p3.x
    ));
}

float N(float t) {
    return fract(sin(t * 12345.564) * 7658.76);
}

float Saw(float b, float t) {
    return S(0.0, b, t) * S(1.0, b, t);
}

vec2 Drops(vec2 uv, float t, float dropSize) {
    vec2 UV = uv;

    uv.y += t * 0.8;
    vec2 a    = u_drop_grid;
    vec2 grid = a * 2.0;
    vec2 id   = floor(uv * grid);

    float colShift = N(id.x);
    uv.y += colShift;

    id = floor(uv * grid);
    vec3 n  = N13(id.x * 35.2 + id.y * 2376.1);
    vec2 st = fract(uv * grid) - vec2(0.5, 0.0);

    float x = n.x - 0.5;

    float y = UV.y * 20.0;
    float distort = sin(y + sin(y));
    x += distort * (0.5 - abs(x)) * (n.z - 0.5);
    x *= 0.7;

    float ti = fract(t + n.z);
    y = (Saw(0.85, ti) - 0.5) * 0.9 + 0.5;
    vec2 p = vec2(x, y);

    float d = length((st - p) * a.yx);
    float Drop = S(dropSize, 0.0, d);

    float r  = sqrt(S(1.0, y, st.y));
    float cd = abs(st.x - x);

    float trail      = S((dropSize * 0.5 + 0.03) * r, (dropSize * 0.5 - 0.05) * r, cd);
    float trailFront = S(-0.02, 0.02, st.y - y);
    trail *= trailFront;

    y = UV.y;
    y += N(id.x);
    float trail2 = S(dropSize * r, 0.0, cd);
    float droplets = max(0.0, (sin(y * (1.0 - y) * 120.0) - st.y)) * trail2 * trailFront * n.z;
    y = fract(y * 10.0) + (st.y - 0.5);
    float dd = length(st - vec2(x, y));
    droplets = S(dropSize * N(id.x), 0.0, dd);

    float m = Drop + droplets * r * trailFront;
    return vec2(m, trail);
}

float StaticDrops(vec2 uv, float t, float dropSize) {
    uv *= 30.0;
    vec2 id = floor(uv);
    uv = fract(uv) - 0.5;
    vec3 n = N13(id.x * 107.45 + id.y * 3543.654);
    vec2 p = (n.xy - 0.5) * 0.5;
    float d = length(uv - p);

    float fade = Saw(0.025, fract(t + n.z));
    return S(dropSize, 0.0, d) * fract(n.z * 10.0) * fade;
}

vec2 Rain(vec2 uv, float t, float dropSize, float rainAmount) {
    float s  = StaticDrops(uv, t, dropSize) * rainAmount;
    vec2  r1 = Drops(uv,        t, dropSize);
    vec2  r2 = Drops(uv * 1.85, t, dropSize) * rainAmount;
    float m  = s + r1.x + r2.x;
    m = S(0.3, 1.0, m);
    return vec2(m, max(r1.y, r2.y));
}

void main() {
    // Heartfelt sampled (uv - .5*res)/res.y so 1 unit ≈ 1 screen height. We do the
    // same so drop sizes stay aspect-correct on any job resolution.
    vec2 uv_centered = (v_uv * u_resolution - 0.5 * u_resolution) / u_resolution.y;
    vec2 UV = (v_uv - 0.5) * u_zoom + 0.5;

    float t = u_t * 0.2;

    vec2 c = Rain(uv_centered, t, u_drop_size, u_rain_amount);

    // Finite differences in UV-pixels for a stable normal at any resolution.
    vec2 e = vec2(1.0 / u_resolution.y, 0.0);
    float cx = Rain(uv_centered + e,    t, u_drop_size, u_rain_amount).x;
    float cy = Rain(uv_centered + e.yx, t, u_drop_size, u_rain_amount).x;
    vec2 n = vec2(cx - c.x, cy - c.x) * u_refraction;

    vec3 blurred = textureLod(u_source, UV + n, u_blur_lod).rgb;
    blurred = mix(blurred, u_glass_tint, clamp(u_glass_opacity, 0.0, 1.0));

    vec3 sharp = texture(u_source, UV + n).rgb;

    float trail = clamp(c.y, 0.0, 1.0);
    vec3 col = blurred;
    col -= trail;
    col += trail * (sharp + 0.6);

    fragColor = vec4(clamp(col, 0.0, 1.0), 1.0);
}
"""

_QUAD = np.array(
    [-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0],
    dtype="f4",
)


class WaterDropsGL(GLPostProcessClip):
    """Rainy window: procedural rain (Heartfelt-derived).

    Cheap by design — no baked textures, no per-frame readback. The frosted-glass
    background uses mipmap LOD off the composited scene; refraction is one extra
    sharp tap.
    """

    clip_type: ClassVar[str] = "std-water-drops-gl"
    clip_license: ClassVar[str] = "CC-BY-NC-SA-3.0"
    clip_category: ClassVar[ClipCategory] = ClipCategory.POSTPROCESS
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED, ClipTag.GL]

    drop_size: float = Field(
        default=0.20,
        ge=0.05,
        le=0.40,
        multiple_of=0.01,
        description="Procedural drop size (smoothstep edge); higher = bigger drops.",
    )
    grid_columns: float = Field(
        default=6.0,
        ge=2.0,
        le=12.0,
        multiple_of=1.0,
        description="Horizontal grid columns for sliding drops.",
    )
    grid_rows: float = Field(
        default=1.0,
        ge=0.5,
        le=4.0,
        multiple_of=0.1,
        description="Vertical grid rows for sliding drops (lower = longer slides).",
    )
    rain_amount: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="How dense the rain is (static drops + second sliding sheet).",
    )
    speed: float = Field(
        default=1.0,
        ge=0.1,
        le=4.0,
        multiple_of=0.1,
        description="Animation speed multiplier (1.0 ≈ original Heartfelt pace).",
    )

    blur_lod: float = Field(
        default=3.0,
        ge=0.0,
        le=6.0,
        multiple_of=1.0,
        description="Mipmap LOD for the frosted-glass background (higher = blurrier).",
    )
    refraction: float = Field(
        default=8.0,
        ge=0.0,
        le=24.0,
        multiple_of=1.0,
        description="Strength of normal-driven refraction inside drops.",
    )
    zoom: float = Field(
        default=0.9,
        ge=0.6,
        le=1.0,
        multiple_of=0.1,
        description="Background recentering (Heartfelt's `(UV-.5)*0.9+.5` trick); slight pull-in.",
    )
    glass_opacity: float = Field(
        default=0.10,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Ambient tint over the blurred background.",
    )
    glass_tint: ColorToken | Color = color_field(ColorToken.BACKGROUND)

    _program: moderngl.Program | None = PrivateAttr(default=None)
    _vao: moderngl.VertexArray | None = PrivateAttr(default=None)

    async def prepare(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        return None

    def _set_uniform(self, prog: moderngl.Program, name: str, value: Any) -> None:
        if name in prog:
            member = prog[name]
            if isinstance(member, moderngl.Uniform):
                member.value = value

    def draw(self, ctx: RenderContext) -> None:
        if ctx.source_texture is None:
            return

        gl: moderngl.Context = ctx.canvas

        ctx.source_texture.build_mipmaps()
        ctx.source_texture.filter = (moderngl.LINEAR_MIPMAP_LINEAR, moderngl.LINEAR)

        if self._program is None:
            self._program = gl.program(vertex_shader=_VERT, fragment_shader=_FRAG)
            vbo = gl.buffer(_QUAD.tobytes())
            self._vao = gl.simple_vertex_array(self._program, vbo, "in_vert")

        prog = self._program

        ctx.source_texture.use(location=0)
        self._set_uniform(prog, "u_source", 0)

        self._set_uniform(prog, "u_resolution", (float(ctx.job.width), float(ctx.job.height)))
        self._set_uniform(prog, "u_t", float(ctx.time.t) * float(self.speed))
        self._set_uniform(prog, "u_drop_size", float(self.drop_size))
        self._set_uniform(prog, "u_rain_amount", float(self.rain_amount))
        self._set_uniform(prog, "u_drop_grid", (float(self.grid_columns), float(self.grid_rows)))
        self._set_uniform(prog, "u_blur_lod", float(self.blur_lod))
        self._set_uniform(prog, "u_refraction", float(self.refraction))
        self._set_uniform(prog, "u_zoom", float(self.zoom))
        self._set_uniform(prog, "u_glass_opacity", float(self.glass_opacity))

        cr, cg, cb, _ = resolve_color(self.glass_tint, ctx.job.colors).rgba
        self._set_uniform(prog, "u_glass_tint", (cr, cg, cb))

        assert self._vao is not None
        self._vao.render(moderngl.TRIANGLES)
