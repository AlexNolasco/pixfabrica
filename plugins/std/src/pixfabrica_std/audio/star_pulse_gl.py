"""Triple-layer star emblem — bass warps the silhouette, amplitude swells size.

Port of a compact Shadertoy hex-star shader (aa_step + star_dist).
Single theme color; three phase-offset layers preserve the sharp moiré read.
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

# Bump when fragment shader changes so cached GL programs recompile.
_SHADER_REVISION = 1

# ── Animation ────────────────────────────────────────────────────────────────
_ROTATION_RATE = 0.1
_LAYER_PHASE = 0.333333333  # 1/3 turn between layers (TAU/3 normalized to 1.0 in shader)

# ── Audio drive (bass → wobble, amplitude → size) ───────────────────────────
_SMOOTHING = 0.45
_BASS_WOBBLE_GAIN = 0.25
_AMP_SIZE_GAIN = 0.35
_AMP_SIZE_MAX = 1.45

# ── Star shape ───────────────────────────────────────────────────────────────
_STAR_REMAP_IN_MIN = -1.0
_STAR_REMAP_IN_MAX = 1.0
_STAR_REMAP_OUT_MIN = 0.75
_STAR_REMAP_OUT_MAX = 1.0
_AA_FEATHER = 1.5
_GAMMA = 2.2

_VERT = """
#version 330 core
in vec2 in_vert;
void main() { gl_Position = vec4(in_vert, 0.0, 1.0); }
"""

_FRAG = f"""
#version 330 core

#define TAU 6.2831853071
#define ROTATION_RATE {_ROTATION_RATE}
#define LAYER_PHASE {_LAYER_PHASE}
#define BASS_WOBBLE_GAIN {_BASS_WOBBLE_GAIN}
#define AA_FEATHER {_AA_FEATHER}
#define GAMMA {_GAMMA}

uniform vec2  u_res;
uniform vec2  u_origin;
uniform float u_canvas_h;
uniform float u_t;
uniform float u_width;
uniform float u_bass_wobble;
uniform float u_amp_size;
uniform float u_points;
uniform vec3  u_color;
uniform float u_offset_x;
uniform float u_offset_y;
uniform float u_luma_alpha;
uniform float u_opacity;

out vec4 frag_color;

float remap(float a, float b, float x, float y, float v) {{
    return (v - a) / (b - a) * (y - x) + x;
}}

float aa_step(float threshold, float x) {{
    float pixel_size = AA_FEATHER / u_res.y;
    return smoothstep(threshold - pixel_size, threshold + pixel_size, x);
}}

float star_dist(vec2 p, float sides, float angle) {{
    float p_angle = atan(p.y, p.x);
    float shape = sin(p_angle * sides + angle * sides);
    return remap({_STAR_REMAP_IN_MIN}, {_STAR_REMAP_IN_MAX},
                 {_STAR_REMAP_OUT_MIN}, {_STAR_REMAP_OUT_MAX}, shape);
}}

void main() {{
    float px = gl_FragCoord.x - u_origin.x;
    float py = (u_canvas_h - gl_FragCoord.y) - u_origin.y;
    if (px < 0.0 || px >= u_res.x || py < 0.0 || py >= u_res.y) discard;

    float cx = u_res.x * u_offset_x;
    float cy = u_res.y * u_offset_y;
    float norm = max(min(u_res.x * 0.5, u_res.y * 0.5), 1.0);
    vec2 uv = vec2(px - cx, cy - py) / norm;

    float size = max(u_width * u_amp_size, 0.05);
    uv /= size;

    float d = length(uv);
    float t = u_t;
    float r = t * TAU * ROTATION_RATE;
    float pscale = u_bass_wobble * BASS_WOBBLE_GAIN;
    float sides = u_points;

    vec3 color = vec3(0.0);
    color += u_color * aa_step(d, star_dist(uv, sides, r + sin(t + LAYER_PHASE * TAU * 0.0) * pscale));
    color += u_color * aa_step(d, star_dist(uv, sides, r + sin(t + LAYER_PHASE * TAU * 1.0) * pscale));
    color += u_color * aa_step(d, star_dist(uv, sides, r + sin(t + LAYER_PHASE * TAU * 2.0) * pscale));

    color = pow(max(color, vec3(0.0)), vec3(1.0 / GAMMA));

    float luma  = dot(color, vec3(0.299, 0.587, 0.114));
    float alpha = mix(1.0, clamp(luma, 0.0, 1.0), u_luma_alpha) * u_opacity;
    frag_color  = vec4(color * alpha, alpha);
}}
"""

_QUAD = np.array(
    [-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0],
    dtype="f4",
)


def _normalize_channel(raw: np.ndarray) -> np.ndarray:
    if raw.size == 0:
        return raw
    lo, hi = np.percentile(raw, (5.0, 95.0))
    span = max(float(hi - lo), 1e-6)
    return np.clip((raw - lo) / span, 0.0, 1.0).astype(np.float32)


def _precompute_audio_drive(
    *,
    total_frames: int,
    bus_frames: list[AudioBusFrame] | None,
    sensitivity: float,
) -> tuple[np.ndarray, np.ndarray]:
    bass_history = np.zeros(max(total_frames, 0), dtype=np.float32)
    amp_history = np.zeros(max(total_frames, 0), dtype=np.float32)
    if total_frames <= 0 or not bus_frames:
        return bass_history, amp_history

    n_bus = min(total_frames, len(bus_frames))
    bass_norm = _normalize_channel(
        np.asarray([float(bus_frames[f].bass) for f in range(n_bus)], dtype=np.float32)
    )
    amp_norm = _normalize_channel(
        np.asarray([float(bus_frames[f].amplitude) for f in range(n_bus)], dtype=np.float32)
    )

    s = float(_SMOOTHING)
    one_minus_s = 1.0 - s
    sens = float(sensitivity)
    bass_acc = 0.0
    amp_acc = 0.0
    for f in range(total_frames):
        if f < n_bus:
            bass_acc = bass_acc * s + float(bass_norm[f]) * one_minus_s
            amp_acc = amp_acc * s + float(amp_norm[f]) * one_minus_s
        else:
            bass_acc *= s
            amp_acc *= s
        bass_history[f] = min(1.0, bass_acc * sens)
        amp_history[f] = min(1.0, amp_acc * sens)
    return bass_history, amp_history


def _amp_size_multiplier(amp_drive: float) -> float:
    swell = max(0.0, float(amp_drive)) * _AMP_SIZE_GAIN
    return min(_AMP_SIZE_MAX, 1.0 + swell)


class StarPulseGL(AudioVisualMixin, ClipGL):
    """Sharp triple-layer star — bass warps points, amplitude swells width, slow spin always."""

    clip_type: ClassVar[str] = "std-star-pulse-gl"
    clip_category: ClassVar[ClipCategory] = ClipCategory.AUDIO
    clip_tags: ClassVar[list[str]] = [ClipTag.AUDIO_REACTIVE, ClipTag.ANIMATED, ClipTag.GL]
    clip_presets: ClassVar[list[ClipPreset]] = [
        ClipPreset(id="default", label="Default", values={}),
        ClipPreset(
            id="overlay",
            label="Overlay",
            values={
                "luma_alpha": 1.0,
                "opacity": 1.0,
            },
        ),
        ClipPreset(
            id="octa_burst",
            label="Octa Burst",
            values={
                "points": 8,
                "width": 0.3,
            },
        ),
    ]

    color: ColorToken | Color = color_field(ColorToken.PRIMARY)
    width: float = Field(
        default=0.4,
        ge=0.1,
        le=1.0,
        multiple_of=0.05,
        description="Star size as a fraction of the shorter bounds half-axis",
    )
    offset_x: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Horizontal center (0=left, 0.5=center, 1=right)",
    )
    offset_y: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Vertical center (0=top, 0.5=center, 1=bottom)",
    )
    speed: float = Field(
        default=1.0,
        ge=0.1,
        le=3.0,
        multiple_of=0.1,
        description="Rotation speed multiplier",
    )
    sensitivity: float = Field(
        default=2.5,
        ge=0.1,
        le=8.0,
        multiple_of=0.1,
        description="Audio response gain on bass wobble and amplitude size swell",
    )
    points: int = Field(
        default=6,
        ge=5,
        le=8,
        multiple_of=1,
        description="Star point count (5–8)",
    )
    luma_alpha: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Luma-based transparency (0 = solid black, 1 = dark areas transparent)",
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
    _bass_history: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype=np.float32))
    _amp_history: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype=np.float32))
    _program: moderngl.Program | None = PrivateAttr(default=None)
    _vao: moderngl.VertexArray | None = PrivateAttr(default=None)
    _shader_revision: int = PrivateAttr(default=0)

    async def prepare(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        b = bounds or Rect(0, 0, ctx.job.width, ctx.job.height)
        self._canvas_h = float(ctx.job.height)
        self._bounds_x = float(b.x)
        self._bounds_y = float(b.y)
        self._bounds_w = float(b.width)
        self._bounds_h = float(b.height)
        self._bass_history, self._amp_history = _precompute_audio_drive(
            total_frames=max(ctx.job.total_frames, 0),
            bus_frames=self.bus_timeline(ctx),
            sensitivity=float(self.sensitivity),
        )
        self._program = None
        self._vao = None
        self._shader_revision = 0

    def _ensure_program(self, gl: moderngl.Context) -> None:
        if self._program is not None and self._shader_revision == _SHADER_REVISION:
            return
        self._program = gl.program(vertex_shader=_VERT, fragment_shader=_FRAG)
        vbo = gl.buffer(_QUAD.tobytes())
        self._vao = gl.simple_vertex_array(self._program, vbo, "in_vert")
        self._shader_revision = _SHADER_REVISION

    def _set_uniform(self, prog: moderngl.Program, name: str, value: Any) -> None:
        if name not in prog:
            return
        member = prog[name]
        if isinstance(member, moderngl.Uniform):
            member.value = value

    def _audio_drive_for_frame(self, ctx: RenderContext) -> tuple[float, float]:
        if not self.bus_active_for_draw(ctx):
            return 0.0, 0.0
        if self._bass_history.size > 0:
            f = max(0, min(ctx.time.frame, self._bass_history.shape[0] - 1))
            return float(self._bass_history[f]), float(self._amp_history[f])
        af = ctx.audio_bus_frame
        sens = float(self.sensitivity)
        bass = min(1.0, max(0.0, float(af.bass)) * sens)
        amp = min(1.0, max(0.0, float(af.amplitude)) * sens)
        return bass, amp

    def draw(self, ctx: RenderContext) -> None:
        gl: moderngl.Context = ctx.canvas
        self._ensure_program(gl)
        prog = self._program
        assert prog is not None

        bass_wobble, amp_drive = self._audio_drive_for_frame(ctx)
        amp_size = _amp_size_multiplier(amp_drive)
        cr, cg, cb, _ = resolve_color(self.color, ctx.job.colors).rgba

        self._set_uniform(prog, "u_res", (self._bounds_w, self._bounds_h))
        self._set_uniform(prog, "u_origin", (self._bounds_x, self._bounds_y))
        self._set_uniform(prog, "u_canvas_h", self._canvas_h)
        self._set_uniform(prog, "u_t", float(ctx.time.t) * float(self.speed))
        self._set_uniform(prog, "u_width", float(self.width))
        self._set_uniform(prog, "u_bass_wobble", bass_wobble)
        self._set_uniform(prog, "u_amp_size", amp_size)
        self._set_uniform(prog, "u_points", float(self.points))
        self._set_uniform(prog, "u_color", (cr, cg, cb))
        self._set_uniform(prog, "u_offset_x", float(self.offset_x))
        self._set_uniform(prog, "u_offset_y", float(self.offset_y))
        self._set_uniform(prog, "u_luma_alpha", float(self.luma_alpha))
        self._set_uniform(prog, "u_opacity", float(self.opacity))

        gl.scissor = (
            int(self._bounds_x),
            int(ctx.job.height - self._bounds_y - ctx.bounds.height),
            int(self._bounds_w),
            int(self._bounds_h),
        )

        assert self._vao is not None
        self._vao.render(moderngl.TRIANGLES)

        gl.scissor = None
