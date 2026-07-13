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
uniform vec3  u_color;
uniform float u_eff_brightness;
uniform float u_luma_alpha;
uniform float u_opacity;

out vec4 frag_color;

// Raymarch steps — original: 100. Lower is faster; ~32 minimum before clouds go thin.
#define STEPS  48
// Noise octave scales — unrolled from a dynamic loop for GPU branch elimination.
#define NA  0.08   // fine detail
#define NB  0.20   // mid
#define NC  0.60   // coarse

// p and u_eff_t are resolved from main() scope at expansion.
#define N(a) abs(dot(sin(u_eff_t + 0.1 * p.z + 0.3 * p / (a)), vec3((a) + (a))))

void main() {
    float px = gl_FragCoord.x - u_origin.x;
    float py = (u_canvas_h - gl_FragCoord.y) - u_origin.y;

    if (px < 0.0 || px >= u_res.x || py < 0.0 || py >= u_res.y) discard;

    vec2 uv = (vec2(px, py) * 2.0 - u_res) / u_res.y;

    float s = 0.0;
    vec4  o = vec4(0.0);
    vec3  p = vec3(0.0);

    for (int step = 0; step < STEPS; step++) {
        p += vec3(uv * s, s);
        s  = 0.1 + 0.2 * abs(6.0 - abs(p.y) - N(NA) - N(NB) - N(NC));
        o += vec4(4.0, 2.0, 1.0, 0.0) / s;
    }

    // Guard against division by zero at the centre pixel.
    // Exposure divisor — original: 2e3. Larger = dimmer; smaller = more blown-out.
    float centre_dist = max(length(uv), 1e-4);
    o = tanh(o / 2000.0 / centre_dist);

    float density = dot(o.rgb, vec3(0.299, 0.587, 0.114));
    vec3 col = density * u_color * u_eff_brightness;

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


class FuzzyCloudsGL(AudioVisualMixin, ClipGL):
    """Volumetric fuzzy clouds — raymarched cloud layer with audio-reactive brightness.
    Designed for slow, hypnotic music visualizations."""

    clip_type: ClassVar[str] = "std-fuzzy-clouds-gl"
    clip_category: ClassVar[ClipCategory] = ClipCategory.BACKGROUND
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED, ClipTag.GL, ClipTag.AUDIO_REACTIVE]
    clip_presets: ClassVar[list[ClipPreset]] = [
        ClipPreset(
            id="hypnotic",
            label="Hypnotic",
            values={
                "speed": 1.0,
                "brightness": 1.0,
                "luma_alpha": 0.0,
                "opacity": 1.0,
            },
        ),
        ClipPreset(
            id="ethereal",
            label="Ethereal",
            values={
                "speed": 1.8,
                "brightness": 1.3,
                "luma_alpha": 0.8,
                "opacity": 0.9,
            },
        ),
    ]

    color_primary: ColorToken | Color = color_field(ColorToken.PRIMARY)
    speed: float = Field(
        default=1.0,
        ge=0.1,
        le=3.0,
        multiple_of=0.1,
        description="Cloud drift speed multiplier (1 = original)",
    )
    brightness: float = Field(
        default=1.0,
        ge=0.2,
        le=3.0,
        multiple_of=0.1,
        description="Cloud brightness multiplier",
    )
    luma_alpha: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Luma-based transparency (0 = solid fill, 1 = dark areas transparent)",
    )
    opacity: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Overall layer opacity",
    )
    bus_intensity: float = Field(
        default=1.0,
        ge=0.0,
        le=2.0,
        multiple_of=0.1,
        description="Audio bus reactivity — scales brightness modulation (0 = off)",
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

        r, g, b, _ = resolve_color(self.color_primary, ctx.job.colors).rgba
        self._set_uniform(prog, "u_color", (r, g, b))
        self._set_uniform(prog, "u_eff_brightness", eff_brightness)
        self._set_uniform(prog, "u_luma_alpha", self.luma_alpha)
        self._set_uniform(prog, "u_opacity", self.opacity)

        gl.scissor = (
            int(self._bounds_x),
            int(ctx.job.height - self._bounds_y - ctx.bounds.height),
            int(self._bounds_w),
            int(self._bounds_h),
        )

        assert self._vao is not None
        self._vao.render(moderngl.TRIANGLES)

        gl.scissor = None
