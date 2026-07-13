from __future__ import annotations

from typing import Any, ClassVar, cast

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
from pixfabrica_std.mesh.shader_helper import precompute_bus_drives
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
uniform float u_eff_t;
uniform vec3  u_color_inner;
uniform vec3  u_color_outer;
uniform float u_brightness;
uniform float u_luma_alpha;
uniform float u_opacity;
uniform float u_angle;

out vec4 frag_color;

// Raymarch steps — match original. The reference sphere sits at depth ~fi=60-80
// depending on canvas size; fewer steps leave too little accumulation headroom.
#define STEPS 100

// Portage of "Ascend" by bµg (CC BY-NC-SA 4.0).
// Original: https://art.pkh.me/2026-02-22-ascend.htm

float octave_noise(vec3 p, float a, float nx, float ny) {
    return abs(dot(sin(p / a * nx), vec3(a * ny)));
}

void main() {
    float px = gl_FragCoord.x - u_origin.x;
    float py = (u_canvas_h - gl_FragCoord.y) - u_origin.y;

    if (px < 0.0 || px >= u_res.x || py < 0.0 || py >= u_res.y) discard;

    // Restore shadertoy Y-up convention: our py is top-to-bottom, shadertoy P.y is
    // bottom-to-top, so centered.y must be negated to match. Without this the motion
    // direction inverts and the reference sphere is displaced off-screen.
    // 0 = up, 90 = right, 180 = down, -90 = left.
    vec2 centered = vec2(px * 2.0 - u_res.x, u_res.y - 2.0 * py);
    float ca = cos(radians(u_angle));
    float sa = sin(radians(u_angle));
    vec2 P = vec2(centered.x * ca - centered.y * sa,
                  centered.x * sa + centered.y * ca);

    // Scale user colors [0,1] to match original accumulation magnitudes (~3).
    vec3 col_in  = u_color_inner * 3.0;
    vec3 col_out = u_color_outer * 3.0;

    vec3  o = vec3(0.0);
    float k = 0.0;
    float s = 0.0;

    for (int step = 0; step < STEPS; step++) {
        float fi = float(step + 1);

        // Build perspective ray for this march step.
        vec3 p = normalize(vec3(P, u_res.y)) * fi * 0.05;
        p.z -= 3.0;

        // Reference sphere at (1.5, 0.7, 0) — drives color blend and specular.
        vec3 q = p - vec3(1.5, 0.7, 0.0);
        s = length(q);               // sphere distance before y clamp / time shift
        q.y = p.y - min(p.y, 0.7);
        float l = length(q);

        p.y += u_eff_t;              // ascent: geometry rises over time
        float d = min(length(p.xz), 1.0 - p.z);

        // Octave noise: a doubles 0.01→0.02→…→2.56 (8 passes)
        float a = 0.01;
        while (a < 3.0) {
            p.zy = p.zy * (0.1 * mat2(8.0, 6.0, -6.0, 8.0));
            d -= octave_noise(p, a, 4.0, 0.2);
            l -= octave_noise(p, a, 5.0, 0.01);
            a += a;
        }

        // First accumulation pass: outer/inner color blend by proximity to sphere.
        float x_val = max(2.0 - l, 0.0) * 0.8;
        d = min(d, 0.0);
        float av = d * k - d;
        k += av;
        o += (av / exp(s * 1.3)) * (1.0 + d) * mix(col_out, col_in, x_val);

        // Second accumulation pass: inner-color specular highlight (q = col_in).
        d = l;
        d = min(d, 0.0);
        av = d * k - d;
        k += av;
        o += (av / exp(s * 1.3)) * (1.0 + d) * col_in * 20.0;

        // Halo term. Use max(s, 1e-4) rather than a guard: the original relies on
        // s approaching zero near the sphere to blow the value out before tanh — that
        // is what creates the bright rocket spike. A hard skip would suppress it.
        o += (x_val - x_val * k) / max(s, 1e-4) / 400.0;
    }

    vec3 col = tanh(o) * u_brightness;
    float luma  = dot(col, vec3(0.299, 0.587, 0.114));
    float alpha = mix(1.0, clamp(luma, 0.0, 1.0), u_luma_alpha) * u_opacity;
    frag_color = vec4(col * alpha, alpha);
}
"""

_QUAD = np.array(
    [-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0],
    dtype="f4",
)


def _precompute_beat_decay(
    frames: list[AudioBusFrame] | None,
    total: int,
) -> np.ndarray:
    history = np.zeros(max(total, 0), dtype=np.float32)
    if total <= 0 or not frames:
        return history
    n_bus = min(total, len(frames))
    d = 0.0
    for f in range(total):
        if f < n_bus:
            d = 1.0 if frames[f].beat else d * 0.85
        else:
            d *= 0.85
        history[f] = d
    return history


class AscendGL(AudioVisualMixin, ClipGL):
    """Raymarched ascending light columns — a volumetric pillar effect that rises
    with the music. Inner/outer colors follow theme tokens; angle rotates the
    ascent direction."""

    clip_type: ClassVar[str] = "std-ascend-gl"
    clip_license: ClassVar[str] = "CC-BY-NC-SA-4.0"
    clip_category: ClassVar[ClipCategory] = ClipCategory.BACKGROUND
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED, ClipTag.GL, ClipTag.AUDIO_REACTIVE]
    clip_presets: ClassVar[list[ClipPreset]] = [
        ClipPreset(
            id="ascend",
            label="Ascend",
            values={
                "speed": 1.0,
                "brightness": 1.0,
                "luma_alpha": 0.0,
                "opacity": 1.0,
            },
        ),
        ClipPreset(
            id="storm",
            label="Storm",
            values={
                "speed": 2.5,
                "brightness": 1.6,
                "luma_alpha": 0.0,
                "opacity": 1.0,
            },
        ),
        ClipPreset(
            id="ethereal",
            label="Ethereal",
            values={
                "speed": 0.5,
                "brightness": 0.8,
                "luma_alpha": 0.7,
                "opacity": 0.8,
            },
        ),
    ]

    color_inner: ColorToken | Color = color_field(ColorToken.PRIMARY)
    color_outer: ColorToken | Color = color_field(ColorToken.SECONDARY)
    angle: float = Field(
        default=0.0,
        ge=ANGLE_FULL_MIN,
        le=ANGLE_FULL_MAX,
        multiple_of=1.0,
        description=ANGLE_FULL_DESC,
    )
    opacity: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Overall layer opacity",
    )
    speed: float = Field(
        default=1.0,
        ge=0.1,
        le=5.0,
        multiple_of=0.1,
        description="Ascent speed multiplier (1 = original)",
    )
    brightness: float = Field(
        default=1.0,
        ge=0.2,
        le=3.0,
        multiple_of=0.1,
        description="Column brightness multiplier",
    )
    luma_alpha: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Luma-based transparency (0 = solid fill, 1 = dark areas transparent)",
    )
    bus_intensity: float = Field(
        default=1.0,
        ge=0.0,
        le=2.0,
        multiple_of=0.1,
        description="Audio bus reactivity — scales brightness on bass hits (0 = off)",
    )
    sensitivity: float = Field(
        default=2.5,
        ge=0.1,
        le=8.0,
        multiple_of=0.1,
        description="Audio response gain on bass brightness after job-wide normalization",
    )

    _canvas_h: float = PrivateAttr(default=0.0)
    _bounds_x: float = PrivateAttr(default=0.0)
    _bounds_y: float = PrivateAttr(default=0.0)
    _bounds_w: float = PrivateAttr(default=0.0)
    _bounds_h: float = PrivateAttr(default=0.0)
    _bass_history: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype="f4"))
    _beat_decay_frames: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype="f4"))
    _program: moderngl.Program | None = PrivateAttr(default=None)
    _vao: moderngl.VertexArray | None = PrivateAttr(default=None)

    async def prepare(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        b = bounds or Rect(0, 0, ctx.job.width, ctx.job.height)
        self._canvas_h = float(ctx.job.height)
        self._bounds_x = float(b.x)
        self._bounds_y = float(b.y)
        self._bounds_w = float(b.width)
        self._bounds_h = float(b.height)

        bus = self.bus_timeline(ctx)
        total = max(ctx.job.total_frames, 0)
        self._bass_history, _, _, _ = precompute_bus_drives(bus, total)
        self._beat_decay_frames = _precompute_beat_decay(bus, total)

    def _set_uniform(self, prog: moderngl.Program, name: str, value: Any) -> None:
        cast(moderngl.Uniform, prog[name]).value = value

    def _audio_drives_for_frame(self, ctx: RenderContext) -> tuple[float, float]:
        if not self.bus_active_for_draw(ctx):
            return 0.0, 0.0
        sens = float(self.sensitivity)
        if self._bass_history.shape[0] > 0:
            f = max(0, min(ctx.time.frame, self._bass_history.shape[0] - 1))
            bass = min(1.0, float(self._bass_history[f]) * sens)
            beat_flash = (
                float(self._beat_decay_frames[f]) if self._beat_decay_frames.shape[0] > 0 else 0.0
            )
        else:
            af = ctx.audio_bus_frame
            bass = self.scale_audio(float(af.bass))
            beat_flash = 1.0 if af.beat else 0.0
        return bass, beat_flash

    def draw(self, ctx: RenderContext) -> None:
        gl: moderngl.Context = ctx.canvas

        if self._program is None:
            self._program = gl.program(vertex_shader=_VERT, fragment_shader=_FRAG)
            vbo = gl.buffer(_QUAD.tobytes())
            self._vao = gl.simple_vertex_array(self._program, vbo, "in_vert")

        prog = self._program
        bass, beat_flash = self._audio_drives_for_frame(ctx)
        mix = float(self.bus_intensity)

        eff_t = ctx.time.t * self.speed
        eff_brightness = self.brightness * (1.0 + (bass * 1.5 + beat_flash * 0.4) * mix)

        self._set_uniform(prog, "u_res", (self._bounds_w, self._bounds_h))
        self._set_uniform(prog, "u_origin", (self._bounds_x, self._bounds_y))
        self._set_uniform(prog, "u_canvas_h", self._canvas_h)
        self._set_uniform(prog, "u_eff_t", eff_t)

        ri, gi, bi, _ = resolve_color(self.color_inner, ctx.job.colors).rgba
        ro, go, bo, _ = resolve_color(self.color_outer, ctx.job.colors).rgba
        self._set_uniform(prog, "u_color_inner", (ri, gi, bi))
        self._set_uniform(prog, "u_color_outer", (ro, go, bo))

        self._set_uniform(prog, "u_brightness", eff_brightness)
        self._set_uniform(prog, "u_luma_alpha", self.luma_alpha)
        self._set_uniform(prog, "u_opacity", self.opacity)
        self._set_uniform(prog, "u_angle", float(self.angle))

        gl.scissor = (
            int(self._bounds_x),
            int(ctx.job.height - self._bounds_y - ctx.bounds.height),
            int(self._bounds_w),
            int(self._bounds_h),
        )

        assert self._vao is not None
        self._vao.render(moderngl.TRIANGLES)

        gl.scissor = None
