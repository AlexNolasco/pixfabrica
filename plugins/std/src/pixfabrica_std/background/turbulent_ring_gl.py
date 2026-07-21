"""Turbulent ring — golfed Shadertoy raymarch (Xor-style torus / turbulence).

Port of a compact ``mainImage`` ring marcher: 80-step raymarch, axis-angle
turbulence, ``tanh`` tonemap. The original ``cos(s + vec4(0,1,2,0))`` RGB
phases are remapped onto three theme color tokens.
"""

from __future__ import annotations

from typing import Any, ClassVar

import moderngl
import numpy as np
from pydantic import Field, PrivateAttr

from pixfabrica_core.audio.bus import AudioBusFrame
from pixfabrica_core.audio.mixin import AudioVisualMixin
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
uniform float u_brightness;
uniform float u_luma_alpha;
uniform float u_opacity;
uniform int   u_steps;
uniform vec3  u_color_a;
uniform vec3  u_color_b;
uniform vec3  u_color_c;

out vec4 frag_color;

void main() {
    float px = gl_FragCoord.x - u_origin.x;
    float py = (u_canvas_h - gl_FragCoord.y) - u_origin.y;
    if (px < 0.0 || px >= u_res.x || py < 0.0 || py >= u_res.y) discard;

    // Shadertoy fragCoord is y-up.
    vec2 I = vec2(px, u_res.y - py);
    vec2 R = u_res;

    float t = u_t;
    float z = 0.0;
    float d = 0.0;
    float s = 0.0;
    // Accumulate the three cos(s+k) phase weights (was RGB in the original).
    vec3 W = vec3(0.0);

    // for(O*=i; i++<8e1; O+=(cos(s+vec4(0,1,2,0))+1.)/d*z) { ... }
    int steps = clamp(u_steps, 16, 120);
    for (int n = 0; n < 120; n++) {
        if (n >= steps) break;

        // Sample point from ray direction (I+I - R.xyy).
        vec3 p = z * normalize(vec3(I + I, 0.0) - R.xyy);
        // Rotation axis
        vec3 a = normalize(cos(vec3(1.0, 2.0, 0.0) + t - d * 8.0));
        // Move camera back 5 units
        p.z += 5.0;
        // Rotated coordinates (a*dot(a,p) - cross(a,p))
        a = a * dot(a, p) - cross(a, p);

        // Turbulence loop: for(d=1.; d++<9.;) a += sin(a*d+t).yzx/d;
        // Body runs with d = 2..9; d is overwritten by the distance estimate next.
        d = 1.0;
        for (int k = 0; k < 8; k++) {
            d += 1.0;
            a += sin(a * d + t).yzx / d;
        }

        // Distance to ring
        s = a.y;
        d = 0.1 * abs(length(p) - 3.0) + 0.04 * abs(s);
        z += d;

        W += (cos(s + vec3(0.0, 1.0, 2.0)) + 1.0) / d * z;
    }

    W = tanh(W / 3e4);
    vec3 col = (u_color_a * W.x + u_color_b * W.y + u_color_c * W.z) * u_brightness;

    float luma = dot(col, vec3(0.299, 0.587, 0.114));
    float alpha = mix(1.0, clamp(luma * 1.5, 0.0, 1.0), u_luma_alpha) * u_opacity;
    frag_color = vec4(col * alpha, alpha);
}
"""

_QUAD = np.array(
    [-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0],
    dtype="f4",
)


def _precompute_amp(
    frames: list[AudioBusFrame] | None,
    total: int,
    sensitivity: float,
) -> np.ndarray:
    history = np.zeros(max(total, 0), dtype=np.float32)
    if total <= 0 or not frames:
        return history
    n_bus = min(total, len(frames))
    sens = float(sensitivity)
    for f in range(total):
        if f < n_bus:
            history[f] = min(1.0, float(frames[f].amplitude) * sens)
        else:
            history[f] = 0.0
    return history


class TurbulentRingGL(AudioVisualMixin, ClipGL):
    """Raymarched turbulent ring — golfed Shadertoy torus with sin-noise warp."""

    clip_type: ClassVar[str] = "std-turbulent-ring-gl"
    clip_category: ClassVar[ClipCategory] = ClipCategory.BACKGROUND
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED, ClipTag.GL, ClipTag.AUDIO_REACTIVE]
    clip_presets: ClassVar[list[ClipPreset]] = [
        ClipPreset(id="default", label="Default", values={}),
        ClipPreset(
            id="portal",
            label="Portal",
            values={"luma_alpha": 1.0, "brightness": 1.2, "steps": 80},
        ),
        ClipPreset(
            id="fast",
            label="Fast Preview",
            values={"steps": 40, "brightness": 1.0},
        ),
        ClipPreset(
            id="master",
            label="Master",
            values={"steps": 100, "brightness": 1.2},
        ),
    ]

    color: ColorToken | Color = color_field(
        ColorToken.PRIMARY,
        description="Theme color for cos(s) phase (was red in the original)",
    )
    color_secondary: ColorToken | Color = color_field(
        ColorToken.SECONDARY,
        description="Theme color for cos(s+1) phase (was green in the original)",
    )
    color_accent: ColorToken | Color = color_field(
        ColorToken.ACCENT,
        description="Theme color for cos(s+2) phase (was blue in the original)",
    )
    speed: float = Field(
        default=1.0,
        ge=0.1,
        le=3.0,
        multiple_of=0.1,
        description="Animation speed multiplier",
    )
    brightness: float = Field(
        default=1.0,
        ge=0.2,
        le=3.0,
        multiple_of=0.1,
        description="Overall brightness after tanh tonemap",
    )
    steps: int = Field(
        default=80,
        ge=16,
        le=120,
        multiple_of=4,
        description="Raymarch steps (80 = original; higher = sharper ring)",
    )
    luma_alpha: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.05,
        description="0 = opaque plate; 1 = punch darks through for stacking",
    )
    opacity: float = Field(default=1.0, ge=0.0, le=1.0, multiple_of=0.05)
    sensitivity: float = Field(
        default=1.0,
        ge=0.1,
        le=8.0,
        multiple_of=0.05,
        description="Amplitude boost to brightness when a bus is wired",
    )

    _canvas_h: float = PrivateAttr(default=0.0)
    _bounds_x: float = PrivateAttr(default=0.0)
    _bounds_y: float = PrivateAttr(default=0.0)
    _bounds_w: float = PrivateAttr(default=0.0)
    _bounds_h: float = PrivateAttr(default=0.0)
    _amp_history: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype=np.float32))
    _program: moderngl.Program | None = PrivateAttr(default=None)
    _vao: moderngl.VertexArray | None = PrivateAttr(default=None)

    async def prepare(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        b = bounds or Rect(0, 0, ctx.job.width, ctx.job.height)
        self._canvas_h = float(ctx.job.height)
        self._bounds_x = float(b.x)
        self._bounds_y = float(b.y)
        self._bounds_w = float(b.width)
        self._bounds_h = float(b.height)
        self._amp_history = _precompute_amp(
            self.bus_timeline(ctx),
            max(ctx.job.total_frames, 0),
            float(self.sensitivity),
        )
        self._program = None
        self._vao = None

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
        amp = 0.0
        if self._amp_history.shape[0] > 0:
            f = max(0, min(ctx.time.frame, self._amp_history.shape[0] - 1))
            amp = float(self._amp_history[f])
        elif self.bus_active_for_draw(ctx):
            amp = min(1.0, float(ctx.audio_bus_frame.amplitude) * float(self.sensitivity))

        brightness = float(self.brightness) * (1.0 + 0.45 * amp)

        ca = resolve_color(self.color, ctx.job.colors).rgba
        cb = resolve_color(self.color_secondary, ctx.job.colors).rgba
        cc = resolve_color(self.color_accent, ctx.job.colors).rgba

        self._set_uniform(prog, "u_res", (self._bounds_w, self._bounds_h))
        self._set_uniform(prog, "u_origin", (self._bounds_x, self._bounds_y))
        self._set_uniform(prog, "u_canvas_h", self._canvas_h)
        self._set_uniform(prog, "u_t", float(ctx.time.t) * float(self.speed))
        self._set_uniform(prog, "u_brightness", brightness)
        self._set_uniform(prog, "u_luma_alpha", float(self.luma_alpha))
        self._set_uniform(prog, "u_opacity", float(self.opacity))
        self._set_uniform(prog, "u_steps", int(self.steps))
        self._set_uniform(prog, "u_color_a", (ca[0], ca[1], ca[2]))
        self._set_uniform(prog, "u_color_b", (cb[0], cb[1], cb[2]))
        self._set_uniform(prog, "u_color_c", (cc[0], cc[1], cc[2]))

        gl.scissor = (
            int(self._bounds_x),
            int(ctx.job.height - self._bounds_y - self._bounds_h),
            int(self._bounds_w),
            int(self._bounds_h),
        )
        assert self._vao is not None
        self._vao.render(moderngl.TRIANGLES)
        gl.scissor = None
