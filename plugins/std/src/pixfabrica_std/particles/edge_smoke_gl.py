"""Edge-emitted volumetric smoke overlay - transparent GL layer for compositing."""

from __future__ import annotations

from typing import Any, ClassVar, Literal, cast

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

# Preview caps - keep scrubbing responsive; final render uses the user's knobs.
_PREVIEW_STEPS_CAP = 32
_PREVIEW_OCTAVES_CAP = 4
_PREVIEW_SHADOW_STEPS_CAP = 2

_EDGE_INDEX = {"bottom": 0.0, "left": 1.0, "top": 2.0, "right": 3.0}

# Shader look defaults (pre-tint greys).
_SMOKE_BRIGHT = (0.96, 0.96, 0.98)
_SMOKE_DARK = (0.20, 0.20, 0.24)

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

uniform float u_edge;
uniform float u_reach;
uniform float u_feather;
uniform float u_flow_speed;
uniform float u_cross_wind;
uniform float u_swirl;
uniform float u_churn_speed;
uniform float u_density;
uniform float u_slab_depth;
uniform vec3  u_smoke_bright;
uniform vec3  u_smoke_dark;
uniform float u_light_power;
uniform float u_ambient;
uniform float u_luma_alpha;
uniform float u_opacity;
uniform float u_steps_f;
uniform float u_octaves_f;
uniform float u_shadow_steps_f;

out vec4 frag_color;

#define FRAME_Y 1.7
#define MAX_STEPS 96
#define MAX_OCTAVES 6
#define MAX_SHADOW_STEPS 6
#define DETAIL_SCALE 1.5

const vec3 LIGHT_DIR = normalize(vec3(0.6, 0.7, -0.5));

float hash(vec3 p) {
    p = fract(p * 0.3183099 + vec3(0.1, 0.2, 0.3));
    p *= 17.0;
    return fract(p.x * p.y * p.z * (p.x + p.y + p.z));
}

float noise(vec3 p) {
    vec3 i = floor(p), f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    return mix(
        mix(
            mix(hash(i + vec3(0, 0, 0)), hash(i + vec3(1, 0, 0)), f.x),
            mix(hash(i + vec3(0, 1, 0)), hash(i + vec3(1, 1, 0)), f.x),
            f.y
        ),
        mix(
            mix(hash(i + vec3(0, 0, 1)), hash(i + vec3(1, 0, 1)), f.x),
            mix(hash(i + vec3(0, 1, 1)), hash(i + vec3(1, 1, 1)), f.x),
            f.y
        ),
        f.z
    );
}

float fbm(vec3 p) {
    float a = 0.5, r = 0.0;
    mat3 m = mat3(
         0.00,  0.80,  0.60,
        -0.80,  0.36, -0.48,
        -0.60, -0.48,  0.64
    );
    int octaves = int(u_octaves_f);
    for (int i = 0; i < MAX_OCTAVES; i++) {
        if (i >= octaves) break;
        r += a * noise(p);
        p = m * p * 2.02;
        a *= 0.5;
    }
    return r;
}

void edgeBasis(float frame_x, out float prog, out vec3 inward, out vec3 along, vec3 p) {
    // inward = smoke travel direction; along = cross-wind axis (edge-relative).
    if (u_edge < 0.5) {
        prog = p.y + FRAME_Y;
        inward = vec3(0.0, 1.0, 0.0);
        along = vec3(1.0, 0.0, 0.0);
    } else if (u_edge < 1.5) {
        prog = p.x + frame_x;
        inward = vec3(1.0, 0.0, 0.0);
        along = vec3(0.0, 1.0, 0.0);
    } else if (u_edge < 2.5) {
        prog = FRAME_Y - p.y;
        inward = vec3(0.0, -1.0, 0.0);
        along = vec3(1.0, 0.0, 0.0);
    } else {
        prog = frame_x - p.x;
        inward = vec3(-1.0, 0.0, 0.0);
        along = vec3(0.0, 1.0, 0.0);
    }
}

float frameSpan(float frame_x) {
  // Travel distance from emitting edge to the opposite edge of the frame.
  bool vertical = (u_edge < 0.5) || (u_edge >= 1.5 && u_edge < 2.5);
  return 2.0 * (vertical ? FRAME_Y : frame_x);
}

float smokeDensity(vec3 p, float time, float frame_x) {
    float prog;
    vec3 inward;
    vec3 along;
    edgeBasis(frame_x, prog, inward, along, p);

    float span = frameSpan(frame_x);
    // reach 0 = wisps at the edge; reach 1 = soft fill across the frame.
    float coverage = span * (0.15 + u_reach * 2.0);
    float k = clamp(prog / max(coverage, 0.001), 0.0, 1.0);
    float envelope = 1.0 - smoothstep(1.0 - u_feather, 1.0, k);
    envelope *= smoothstep(-0.5, 0.1, prog);
    envelope *= smoothstep(u_slab_depth, u_slab_depth * 0.35, abs(p.z));
    if (envelope <= 0.0) return 0.0;

    // Flow is always edge-relative: push inward + optional cross-wind along the edge.
    vec3 flow = inward * u_flow_speed + along * u_cross_wind;
    // Stronger advection so flow_speed reads clearly against swirl/churn.
    vec3 np = p * DETAIL_SCALE - flow * time * 1.75;

    vec3 warp = vec3(
        fbm(np + inward * (time * u_churn_speed)),
        fbm(np + vec3(5.2, 1.3, 2.8)),
        fbm(np + vec3(1.7, 9.2, 3.1))
    );
    float d = fbm(np + u_swirl * warp);
    d = smoothstep(0.32 + 0.38 * k, 0.85, d);
    // Traveling stream bands so changing flow_speed visibly changes motion rate.
    float stream = 0.72 + 0.28 * sin((prog - time * u_flow_speed) * 1.85);
    d *= stream;
    return clamp(d * envelope * u_density, 0.0, 1.0);
}

float lightMarch(vec3 p, float time, float frame_x) {
    int shadow_steps = int(u_shadow_steps_f);
    if (shadow_steps <= 0) return 1.0;

    float acc = 0.0;
    float stp = 0.22;
    for (int i = 1; i <= MAX_SHADOW_STEPS; i++) {
        if (i > shadow_steps) break;
        acc += smokeDensity(p + LIGHT_DIR * stp * float(i), time, frame_x);
    }
    return exp(-acc * stp * u_light_power * 2.0);
}

void main() {
    float px = gl_FragCoord.x - u_origin.x;
    float py = (u_canvas_h - gl_FragCoord.y) - u_origin.y;

    if (px < 0.0 || px >= u_res.x || py < 0.0 || py >= u_res.y) discard;

    // Shadertoy-style Y-up UV so edge directions match the source shader.
    vec2 uv = (vec2(px, py) - u_res * 0.5) / u_res.y;
    uv.y = -uv.y;

    float frame_x = FRAME_Y * u_res.x / max(u_res.y, 1.0);
    float time = u_t;

    vec3 ro = vec3(0.0, 0.0, 5.0);
    vec3 rd = normalize(vec3(uv, -1.47));

    float near = 5.0 - u_slab_depth - 0.2;
    float far = 5.0 + u_slab_depth + 0.2;
    int steps = int(u_steps_f);
    float step_len = (far - near) / max(float(steps), 1.0);
    float dither = fract(sin(dot(vec2(px, py), vec2(12.9898, 78.233))) * 43758.5453);
    float t_ray = near + step_len * dither;

    vec3 acc = vec3(0.0);
    float trans = 1.0;

    for (int i = 0; i < MAX_STEPS; i++) {
        if (i >= steps) break;
        vec3 p = ro + rd * t_ray;
        float dens = smokeDensity(p, time, frame_x);
        if (dens > 0.001) {
            float lit = lightMarch(p, time, frame_x);
            vec3 smoke_col = mix(u_smoke_dark, u_smoke_bright, lit)
                + u_ambient * u_smoke_dark;
            float alpha = 1.0 - exp(-dens * step_len * 3.0);
            acc += smoke_col * alpha * trans;
            trans *= 1.0 - alpha;
            if (trans < 0.01) break;
        }
        t_ray += step_len;
    }

    float cover = 1.0 - trans;
    vec3 smoke_rgb = acc / max(cover, 1e-4);
    float alpha = mix(1.0, cover, u_luma_alpha) * u_opacity;
    frag_color = vec4(smoke_rgb * alpha, alpha);
}
"""

_QUAD = np.array(
    [-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0],
    dtype="f4",
)


class EdgeSmokeGL(ClipGL):
    """Edge-emitted volumetric smoke - transparent overlay for stacking over backgrounds.

    Smoke enters from a full frame edge and dissipates into wisps as it travels inward.
    """

    clip_type: ClassVar[str] = "std-edge-smoke-gl"
    clip_category: ClassVar[ClipCategory] = ClipCategory.PARTICLES
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED, ClipTag.LOOP, ClipTag.GL, ClipTag.PARTICLE]
    clip_presets: ClassVar[list[ClipPreset]] = [
        ClipPreset(
            id="rising_fog",
            label="Rising Fog",
            values={
                "edge": "bottom",
                "reach": 0.55,
                "feather": 0.7,
                "flow_speed": 1.6,
                "cross_wind": 0.15,
                "swirl": 2.2,
                "churn_speed": 0.35,
                "density": 1.0,
                "slab_depth": 1.1,
                "light_power": 1.2,
                "ambient": 0.6,
                "opacity": 0.9,
                "luma_alpha": 1.0,
                "steps": 48,
                "octaves": 5,
                "shadow_steps": 2,
            },
        ),
        ClipPreset(
            id="side_drift",
            label="Side Drift",
            values={
                "edge": "left",
                "reach": 0.75,
                "feather": 0.55,
                "flow_speed": 2.4,
                "cross_wind": 0.35,
                "swirl": 2.8,
                "churn_speed": 0.55,
                "density": 1.2,
                "slab_depth": 1.1,
                "light_power": 1.4,
                "ambient": 0.4,
                "opacity": 1.0,
                "luma_alpha": 1.0,
                "steps": 64,
                "octaves": 6,
                "shadow_steps": 3,
            },
        ),
    ]

    color: ColorToken | Color = color_field(ColorToken.NEUTRAL_VARIANT)
    edge: Literal["bottom", "left", "top", "right"] = Field(
        default="bottom",
        description="Frame edge the smoke enters from",
    )
    reach: float = Field(
        default=0.85,
        ge=0.1,
        le=1.0,
        multiple_of=0.05,
        description="How far smoke fills the frame from its edge (0 = wisps only, 1 = full soft fill)",
    )
    feather: float = Field(
        default=0.55,
        ge=0.05,
        le=1.0,
        multiple_of=0.05,
        description="How gradually the leading edge dissolves into wisps",
    )
    flow_speed: float = Field(
        default=2.55,
        ge=0.1,
        le=6.0,
        multiple_of=0.05,
        description="How fast smoke streams inward from the chosen edge",
    )
    cross_wind: float = Field(
        default=0.25,
        ge=-2.0,
        le=2.0,
        multiple_of=0.05,
        description="Sideways drift along the emitting edge (edge-relative; no re-aim when edge changes)",
    )
    swirl: float = Field(
        default=2.5,
        ge=0.0,
        le=5.0,
        multiple_of=0.1,
        description="Domain-warp amount - curling / tumbling",
    )
    churn_speed: float = Field(
        default=0.5,
        ge=0.0,
        le=2.0,
        multiple_of=0.05,
        description="How fast the internal turbulence boils",
    )
    density: float = Field(
        default=1.3,
        ge=0.1,
        le=3.0,
        multiple_of=0.1,
        description="Thickness of the smoke",
    )
    slab_depth: float = Field(
        default=1.1,
        ge=0.3,
        le=2.5,
        multiple_of=0.1,
        description="Depth of the smoke volume (thicker = more parallax)",
    )
    light_power: float = Field(
        default=1.4,
        ge=0.0,
        le=3.0,
        multiple_of=0.1,
        description="Self-shadow strength",
    )
    ambient: float = Field(
        default=0.45,
        ge=0.0,
        le=1.5,
        multiple_of=0.05,
        description="Fill light - raise for hazy daylight, lower for moody",
    )
    luma_alpha: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Luma-based transparency (1 = empty areas transparent, 0 = solid fill)",
    )
    opacity: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Overall layer opacity",
    )
    steps: int = Field(
        default=64,
        ge=16,
        le=96,
        multiple_of=8.0,
        description="Raymarch steps (higher = richer, slower)",
    )
    octaves: int = Field(
        default=6,
        ge=3,
        le=6,
        multiple_of=1.0,
        description="Noise octaves (higher = wispier detail)",
    )
    shadow_steps: int = Field(
        default=3,
        ge=0,
        le=6,
        multiple_of=1.0,
        description="Self-shadow samples (0 = flat, faster)",
    )

    _canvas_h: float = PrivateAttr(default=0.0)
    _bounds_x: float = PrivateAttr(default=0.0)
    _bounds_y: float = PrivateAttr(default=0.0)
    _bounds_w: float = PrivateAttr(default=0.0)
    _bounds_h: float = PrivateAttr(default=0.0)
    _for_preview: bool = PrivateAttr(default=False)
    _program: moderngl.Program | None = PrivateAttr(default=None)
    _vao: moderngl.VertexArray | None = PrivateAttr(default=None)

    async def prepare(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        b = bounds or Rect(0, 0, ctx.job.width, ctx.job.height)
        self._canvas_h = float(ctx.job.height)
        self._bounds_x = float(b.x)
        self._bounds_y = float(b.y)
        self._bounds_w = float(b.width)
        self._bounds_h = float(b.height)
        self._for_preview = bool(ctx.for_preview)

    def _set_uniform(self, prog: moderngl.Program, name: str, value: Any) -> None:
        cast(moderngl.Uniform, prog[name]).value = value

    def _effective_quality(self) -> tuple[int, int, int]:
        steps = int(self.steps)
        octaves = int(self.octaves)
        shadow_steps = int(self.shadow_steps)
        if self._for_preview:
            steps = min(steps, _PREVIEW_STEPS_CAP)
            octaves = min(octaves, _PREVIEW_OCTAVES_CAP)
            shadow_steps = min(shadow_steps, _PREVIEW_SHADOW_STEPS_CAP)
        return steps, octaves, shadow_steps

    def draw(self, ctx: RenderContext) -> None:
        gl: moderngl.Context = ctx.canvas

        if self._program is None:
            self._program = gl.program(vertex_shader=_VERT, fragment_shader=_FRAG)
            vbo = gl.buffer(_QUAD.tobytes())
            self._vao = gl.simple_vertex_array(self._program, vbo, "in_vert")

        prog = self._program
        tr, tg, tb, _ = resolve_color(self.color, ctx.job.colors).rgba
        bright = (
            _SMOKE_BRIGHT[0] * tr,
            _SMOKE_BRIGHT[1] * tg,
            _SMOKE_BRIGHT[2] * tb,
        )
        dark = (
            _SMOKE_DARK[0] * tr,
            _SMOKE_DARK[1] * tg,
            _SMOKE_DARK[2] * tb,
        )
        steps, octaves, shadow_steps = self._effective_quality()

        self._set_uniform(prog, "u_res", (self._bounds_w, self._bounds_h))
        self._set_uniform(prog, "u_origin", (self._bounds_x, self._bounds_y))
        self._set_uniform(prog, "u_canvas_h", self._canvas_h)
        self._set_uniform(prog, "u_t", float(ctx.time.t))
        self._set_uniform(prog, "u_edge", _EDGE_INDEX[self.edge])
        self._set_uniform(prog, "u_reach", float(self.reach))
        self._set_uniform(prog, "u_feather", float(self.feather))
        self._set_uniform(prog, "u_flow_speed", float(self.flow_speed))
        self._set_uniform(prog, "u_cross_wind", float(self.cross_wind))
        self._set_uniform(prog, "u_swirl", float(self.swirl))
        self._set_uniform(prog, "u_churn_speed", float(self.churn_speed))
        self._set_uniform(prog, "u_density", float(self.density))
        self._set_uniform(prog, "u_slab_depth", float(self.slab_depth))
        self._set_uniform(prog, "u_smoke_bright", bright)
        self._set_uniform(prog, "u_smoke_dark", dark)
        self._set_uniform(prog, "u_light_power", float(self.light_power))
        self._set_uniform(prog, "u_ambient", float(self.ambient))
        self._set_uniform(prog, "u_luma_alpha", float(self.luma_alpha))
        self._set_uniform(prog, "u_opacity", float(self.opacity))
        self._set_uniform(prog, "u_steps_f", float(steps))
        self._set_uniform(prog, "u_octaves_f", float(octaves))
        self._set_uniform(prog, "u_shadow_steps_f", float(shadow_steps))

        gl.scissor = (
            int(self._bounds_x),
            int(ctx.job.height - self._bounds_y - ctx.bounds.height),
            int(self._bounds_w),
            int(self._bounds_h),
        )

        assert self._vao is not None
        self._vao.render(moderngl.TRIANGLES)

        gl.scissor = None
