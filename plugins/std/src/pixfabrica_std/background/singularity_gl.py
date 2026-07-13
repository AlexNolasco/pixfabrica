"""Whirling blackhole background — port of "Singularity" by @XorDev (Shadertoy).

Original shader: https://www.shadertoy.com/view/3csSWB (CC BY-NC-SA).
Theme-aware two-tone port: the original hardcoded red/blue gradient is
remapped onto two theme color tokens mixed by the same screen-x exponent.
"""

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
uniform float u_zoom;
uniform vec3  u_color_hot;
uniform vec3  u_color_cold;
uniform float u_eff_brightness;
uniform float u_rim_flare;
uniform float u_luma_alpha;
uniform float u_opacity;

out vec4 frag_color;

// "Singularity" by @XorDev — golfed Shadertoy original unpacked for GLSL 330.
// The 1-exp(-exp(...)) tone curve is kept; the per-channel red/blue exponent
// vector (.6, -.4, -1) collapses to two scalar fields mixed by theme colors.

void main() {
    float px = gl_FragCoord.x - u_origin.x;
    float py = (u_canvas_h - gl_FragCoord.y) - u_origin.y;

    if (px < 0.0 || px >= u_res.x || py < 0.0 || py >= u_res.y) discard;

    // Shadertoy fragCoord is y-up; flip so the swirl spins like the original.
    vec2 F = vec2(px, u_res.y - py);

    // Centered ratio-corrected coordinates. 0.7 = original framing.
    vec2 p = (F + F - u_res) / u_res.y / (0.7 * u_zoom);

    // Diagonal vector for skewing
    vec2 d = vec2(-1.0, 1.0);
    float i0 = 0.2;
    // Blackhole center
    vec2 b = p - i0 * d;
    // Rotate and apply perspective
    vec2 c = p * mat2(1.0, 1.0, d / (0.1 + i0 / dot(b, b)));
    // Attenuation (distance-squared); guarded — original divides 1/a at centre.
    float a = max(dot(c, c), 1e-6);
    // Rotate into spiraling coordinates
    vec2 v = c * mat2(cos(0.5 * log(a) + u_eff_t * i0 + vec4(0.0, 33.0, 11.0, 0.0))) / i0;

    // Waves cumulative total for coloring (original leaves w uninitialized)
    vec2 w = vec2(0.0);
    float i = i0;
    for (int n = 0; n < 9; n++) {
        i += 1.0;
        v += 0.7 * sin(v.yx * i + u_eff_t) / i + 0.5;
        w += 1.0 + sin(v);
    }

    // Accretion disk radius
    float disk = length(sin(v / 0.3) * 0.4 + c * (3.0 + d));
    // Rim highlight ring; beat flare widens and brightens it
    float rim = 0.03 + abs(length(p) - 0.7) / (1.0 + 1.5 * u_rim_flare);
    float denom = (2.0 + disk * disk / 4.0 - disk) * (0.5 + 1.0 / a) * rim;

    float hot  = 1.0 - exp(-exp(c.x *  0.6) / max(w.x, 1e-4) / denom);
    float cold = 1.0 - exp(-exp(c.x * -1.0) / max(w.y, 1e-4) / denom);

    vec3 col = (u_color_hot * hot + u_color_cold * cold) * u_eff_brightness;

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


class SingularityGL(AudioVisualMixin, ClipGL):
    """Whirling blackhole — spiraling accretion disk with a bright rim ring.
    Bass drives brightness; beats flare the rim. Two-tone theme gradient."""

    clip_type: ClassVar[str] = "std-singularity-gl"
    clip_license: ClassVar[str] = "CC-BY-NC-SA-3.0"
    clip_category: ClassVar[ClipCategory] = ClipCategory.BACKGROUND
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED, ClipTag.GL, ClipTag.AUDIO_REACTIVE]
    clip_presets: ClassVar[list[ClipPreset]] = [
        ClipPreset(
            id="classic",
            label="Classic",
            values={
                "speed": 1.0,
                "brightness": 1.0,
                "luma_alpha": 0.0,
                "opacity": 1.0,
            },
        ),
        ClipPreset(
            id="portal",
            label="Portal",
            values={
                "speed": 1.0,
                "brightness": 1.3,
                "luma_alpha": 1.0,
                "opacity": 1.0,
            },
        ),
    ]

    color_hot: ColorToken | Color = color_field(ColorToken.PRIMARY)
    color_cold: ColorToken | Color = color_field(ColorToken.SECONDARY)
    speed: float = Field(
        default=1.0,
        ge=0.1,
        le=3.0,
        multiple_of=0.1,
        description="Swirl speed multiplier (1 = original)",
    )
    brightness: float = Field(
        default=1.0,
        ge=0.2,
        le=3.0,
        multiple_of=0.1,
        description="Overall brightness multiplier",
    )
    zoom: float = Field(
        default=1.0,
        ge=0.5,
        le=2.0,
        multiple_of=0.1,
        description="Blackhole size (1 = original framing, higher = larger)",
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
        description="Audio bus reactivity — bass scales brightness, beats flare the rim (0 = off)",
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
        eff_brightness = self.brightness * (1.0 + bass * 0.8 * mix)
        rim_flare = beat_flash * mix

        self._set_uniform(prog, "u_res", (self._bounds_w, self._bounds_h))
        self._set_uniform(prog, "u_origin", (self._bounds_x, self._bounds_y))
        self._set_uniform(prog, "u_canvas_h", self._canvas_h)
        self._set_uniform(prog, "u_eff_t", eff_t)
        self._set_uniform(prog, "u_zoom", self.zoom)

        hr, hg, hb, _ = resolve_color(self.color_hot, ctx.job.colors).rgba
        cr, cg, cb, _ = resolve_color(self.color_cold, ctx.job.colors).rgba
        self._set_uniform(prog, "u_color_hot", (hr, hg, hb))
        self._set_uniform(prog, "u_color_cold", (cr, cg, cb))
        self._set_uniform(prog, "u_eff_brightness", eff_brightness)
        self._set_uniform(prog, "u_rim_flare", rim_flare)
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
