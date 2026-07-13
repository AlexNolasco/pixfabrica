from __future__ import annotations

import colorsys
from typing import Any, ClassVar, cast

import moderngl
import numpy as np
from pydantic import Field, PrivateAttr

from pixfabrica_core.audio.bus import AudioBusFrame
from pixfabrica_core.audio.mixin import AudioVisualMixin
from pixfabrica_core.clips import ClipCategory, ClipGL, ClipTag, PrepareContext, RenderContext
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
uniform float u_t;
uniform float u_bpm;
uniform float u_hue;
uniform float u_hue_range;
uniform float u_intensity;
uniform float u_luma_alpha;
uniform float u_opacity;
uniform float u_offset_x;
uniform float u_offset_y;
uniform float u_beat;
uniform float u_bass;
uniform float u_high;
uniform float u_amplitude;

out vec4 frag_color;

#define TWO_PI        6.283185307
#define SEG           6.0
#define L_KALEIDO     0.6
#define L_WAVES       0.9
#define L_HEART       1.0
#define BEAT_BASE_SCALE 0.1

vec3 hsv2rgb(vec3 c) {
    vec3 p = abs(fract(c.x + vec3(0.0, 2.0/3.0, 1.0/3.0)) * 6.0 - 3.0);
    return c.z * mix(vec3(1.0), clamp(p - 1.0, 0.0, 1.0), c.y);
}

vec3 pal(float t) {
    float h = u_hue + (fract(t) - 0.5) * u_hue_range;
    float v = 0.55 + 0.45 * cos(TWO_PI * t);
    return hsv2rgb(vec3(fract(h), 0.65, v));
}

float sdHeart(in vec2 p) {
    p *= 1.5; p.x = abs(p.x);
    if (p.y + p.x > 1.0)
        return sqrt(dot(p - vec2(0.25, 0.75), p - vec2(0.25, 0.75))) - sqrt(2.0) / 4.0;
    return sqrt(min(
        dot(p - vec2(0.0, 1.0), p - vec2(0.0, 1.0)),
        dot(p - 0.5 * max(p.x + p.y, 0.0), p - 0.5 * max(p.x + p.y, 0.0))
    )) * sign(p.x - p.y);
}

// Bus-driven decay takes priority; BPM clock runs as fallback when bus is silent.
float beatPulse(float BEAT) {
    return max(u_beat, exp(-fract(BEAT) * 5.0));
}

void main() {
    float px = gl_FragCoord.x - u_origin.x;
    float py = (u_canvas_h - gl_FragCoord.y) - u_origin.y;

    if (px < 0.0 || px >= u_res.x || py < 0.0 || py >= u_res.y) discard;

    vec2 uv = (vec2(px, py) * 2.0 - u_res) / u_res.y;
    uv.y  = -uv.y;
    uv.x -= (u_offset_x - 0.5) * 2.0;
    uv.y -= (0.5 - u_offset_y) * 2.0;

    float BEAT = u_t * u_bpm / 60.0;
    float bp   = beatPulse(BEAT);
    vec3  col  = vec3(0.0);

    // Layer 1: kaleidoscope heart field — treble speeds up rotation
    {
        float a = atan(uv.y, uv.x);
        float r = length(uv);
        a = mod(a, TWO_PI / SEG);
        a = abs(a - 3.14159265 / SEG);
        a += u_t * (0.2 + u_high * 0.15);
        vec2 p = vec2(cos(a), sin(a)) * r * 3.0;
        p.x = fract(p.x) - 0.5;
        p.y += 0.35 - 1.0;
        float d = sdHeart(p * (1.0 + 0.15 * bp));
        col += pal(r + 0.2 * BEAT) * exp(-abs(d) * 7.0) * L_KALEIDO;
    }

    // Layer 2: concentric wave rings — bass brightens waves
    {
        vec2 hp = uv / 0.5;
        hp.y += 0.35;
        float d = sdHeart(hp);

        float ring     = 0.0;
        float halfBeat = BEAT * 2.0;
        for (float k = 0.0; k < 10.0; k++) {
            float age    = fract(halfBeat) + k;
            float w      = exp(-abs(d - age * 0.35) * 9.0);
            float bright = mix(1.0, 0.4, mod(floor(halfBeat) - k, 2.0));
            w *= exp(-age * 0.15);
            ring += w * bright;
        }
        ring *= smoothstep(0.0, 0.05, d);
        col += pal(d * 0.5 + 0.1 * BEAT) * ring * (L_WAVES + u_bass * 0.4);
    }

    // Layer 3: central beating heart — bass amplifies scale, beat drives pulse
    {
        float beat2      = exp(-fract(BEAT * 2.0) * 6.0) * 0.5;
        float beat_scale = BEAT_BASE_SCALE * (1.0 + u_bass * 1.5);
        vec2  hp         = uv / (0.5 + beat_scale * (bp + beat2));
        hp.y += 0.35;
        float d  = sdHeart(hp);
        vec3  hc = pal(0.3 + 0.03 * sin(BEAT * TWO_PI));
        col += hc * smoothstep(0.02, -0.02, d) * 1.2 * L_HEART;
        col += hc * exp(-abs(d) * 6.0)          * 0.8 * L_HEART;
        col += hc * exp(-max(d, 0.0) * 4.0)     * 0.4 * L_HEART;
        col *= 1.0 + bp * 0.2;
    }

    col *= u_intensity * (1.0 + u_amplitude * 0.3);

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
            d = 1.5 if frames[f].beat else d * 0.82
        else:
            d *= 0.82
        history[f] = d
    return history


class HeartDanceGL(AudioVisualMixin, ClipGL):
    """Three-layer heart background: kaleidoscope field, concentric wave rings, and a central
    beating heart — audio-reactive via bass (wave intensity, heart scale), beat (pulse),
    treble (kaleido rotation), and amplitude (global brightness)."""

    clip_type: ClassVar[str] = "std-heart-dance-gl"
    clip_category: ClassVar[ClipCategory] = ClipCategory.BACKGROUND
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED, ClipTag.GL, ClipTag.AUDIO_REACTIVE]

    color_primary: ColorToken | Color = color_field(ColorToken.PRIMARY)
    hue_range: float = Field(
        default=0.1,
        ge=0.0,
        le=0.5,
        multiple_of=0.01,
        description="Color spread around the primary hue (0 = monochrome, 0.5 = wide)",
    )
    offset_x: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Horizontal position (0 = left, 0.5 = center, 1 = right)",
    )
    offset_y: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Vertical position (0 = top, 0.5 = center, 1 = bottom)",
    )
    opacity: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Overall layer opacity",
    )
    bpm: float = Field(
        default=120.0,
        ge=40.0,
        le=240.0,
        multiple_of=1.0,
        description="Beats per minute — drives animation phase and fallback pulse when no bus is connected",
    )
    intensity: float = Field(
        default=1.0,
        ge=0.0,
        le=2.0,
        multiple_of=0.05,
        description="Overall brightness multiplier",
    )
    luma_alpha: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Luma-based transparency (0 = solid, 1 = dark areas transparent)",
    )
    sensitivity: float = Field(
        default=2.5,
        ge=0.1,
        le=8.0,
        multiple_of=0.1,
        description="Audio response gain on bass/high/amplitude after job-wide normalization",
    )

    _canvas_h: float = PrivateAttr(default=0.0)
    _bounds_x: float = PrivateAttr(default=0.0)
    _bounds_y: float = PrivateAttr(default=0.0)
    _bounds_w: float = PrivateAttr(default=0.0)
    _bounds_h: float = PrivateAttr(default=0.0)
    _bass_history: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype="f4"))
    _high_history: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype="f4"))
    _amp_history: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype="f4"))
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
        self._bass_history, _, self._high_history, self._amp_history = precompute_bus_drives(
            bus,
            total,
        )
        self._beat_decay_frames = _precompute_beat_decay(bus, total)

    def _set_uniform(self, prog: moderngl.Program, name: str, value: Any) -> None:
        cast(moderngl.Uniform, prog[name]).value = value

    def _audio_drives_for_frame(
        self,
        ctx: RenderContext,
    ) -> tuple[float, float, float, float]:
        if not self.bus_active_for_draw(ctx):
            return 0.0, 0.0, 0.0, 0.0
        sens = float(self.sensitivity)
        if self._bass_history.shape[0] > 0:
            f = max(0, min(ctx.time.frame, self._bass_history.shape[0] - 1))
            bass = min(1.0, float(self._bass_history[f]) * sens)
            high = min(1.0, float(self._high_history[f]) * sens)
            amp = min(1.0, float(self._amp_history[f]) * sens)
            beat = (
                float(self._beat_decay_frames[f]) if self._beat_decay_frames.shape[0] > 0 else 0.0
            )
        else:
            af = ctx.audio_bus_frame
            bass = self.scale_audio(float(af.bass))
            high = self.scale_audio(float(af.high))
            amp = self.scale_audio(float(af.amplitude))
            beat = 1.5 if af.beat else 0.0
        return bass, high, amp, beat

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
        self._set_uniform(prog, "u_bpm", self.bpm)

        r, g, b, _ = resolve_color(self.color_primary, ctx.job.colors).rgba
        h, _s, _v = colorsys.rgb_to_hsv(r, g, b)
        self._set_uniform(prog, "u_hue", h)
        self._set_uniform(prog, "u_hue_range", self.hue_range)

        self._set_uniform(prog, "u_intensity", self.intensity)
        self._set_uniform(prog, "u_luma_alpha", self.luma_alpha)
        self._set_uniform(prog, "u_opacity", self.opacity)
        self._set_uniform(prog, "u_offset_x", self.offset_x)
        self._set_uniform(prog, "u_offset_y", self.offset_y)

        bass, high, amp, beat = self._audio_drives_for_frame(ctx)
        self._set_uniform(prog, "u_beat", beat)
        self._set_uniform(prog, "u_bass", bass)
        self._set_uniform(prog, "u_high", high)
        self._set_uniform(prog, "u_amplitude", amp)

        gl.scissor = (
            int(self._bounds_x),
            int(ctx.job.height - self._bounds_y - ctx.bounds.height),
            int(self._bounds_w),
            int(self._bounds_h),
        )

        assert self._vao is not None
        self._vao.render(moderngl.TRIANGLES)

        gl.scissor = None
