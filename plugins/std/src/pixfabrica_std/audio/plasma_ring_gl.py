from __future__ import annotations

from typing import Any, ClassVar

import moderngl
import numpy as np
from pydantic import Field, PrivateAttr

from pixfabrica_core.audio.bus import AudioBusFrame
from pixfabrica_core.audio.mixin import AudioVisualMixin
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
uniform float u_inner_radius;
uniform float u_noise_scale;
uniform float u_opacity;
uniform vec3  u_color1;
uniform vec3  u_color2;
uniform vec3  u_color3;
uniform float u_offset_x;
uniform float u_offset_y;

out vec4 frag_color;

// Simplex noise — hash and snoise3 from https://www.shadertoy.com/view/4sc3z2
vec3 hash33(vec3 p3)
{
    p3 = fract(p3 * vec3(.1031, .11369, .13787));
    p3 += dot(p3, p3.yxz + 19.19);
    return -1.0 + 2.0 * fract(vec3(p3.x + p3.y, p3.x + p3.z, p3.y + p3.z) * p3.zyx);
}

float snoise3(vec3 p)
{
    const float K1 = 0.333333333;
    const float K2 = 0.166666667;
    vec3 i  = floor(p + (p.x + p.y + p.z) * K1);
    vec3 d0 = p - (i - (i.x + i.y + i.z) * K2);
    vec3 e  = step(vec3(0.0), d0 - d0.yzx);
    vec3 i1 = e * (1.0 - e.zxy);
    vec3 i2 = 1.0 - e.zxy * (1.0 - e);
    vec3 d1 = d0 - (i1 - K2);
    vec3 d2 = d0 - (i2 - K1);
    vec3 d3 = d0 - 0.5;
    vec4 h  = max(0.6 - vec4(dot(d0, d0), dot(d1, d1), dot(d2, d2), dot(d3, d3)), 0.0);
    vec4 n  = h * h * h * h * vec4(
        dot(d0, hash33(i)),
        dot(d1, hash33(i + i1)),
        dot(d2, hash33(i + i2)),
        dot(d3, hash33(i + 1.0))
    );
    return dot(vec4(31.316), n);
}

// Luma-based straight-alpha: bright regions opaque, dark regions transparent.
vec4 extractAlpha(vec3 colorIn)
{
    float maxValue = min(max(max(colorIn.r, colorIn.g), colorIn.b), 1.0);
    if (maxValue > 1e-5)
        return vec4(colorIn * (1.0 / maxValue), maxValue);
    return vec4(0.0);
}

float light1(float intensity, float attenuation, float dist)
{
    return intensity / (1.0 + dist * attenuation);
}

float light2(float intensity, float attenuation, float dist)
{
    return intensity / (1.0 + dist * dist * attenuation);
}

void main()
{
    float px = gl_FragCoord.x - u_origin.x;
    float py = (u_canvas_h - gl_FragCoord.y) - u_origin.y;

    if (px < 0.0 || px >= u_res.x || py < 0.0 || py >= u_res.y) discard;

    float cx   = u_res.x * u_offset_x;
    float cy   = u_res.y * u_offset_y;
    float norm = max(min(u_res.x * 0.5, u_res.y * 0.5), 1.0);
    vec2  uv   = vec2(px - cx, cy - py) / norm;

    float ang = atan(uv.y, uv.x);
    float len = length(uv);

    // ring
    float n0 = snoise3(vec3(uv * u_noise_scale, u_t * 0.5)) * 0.5 + 0.5;
    float r0 = mix(mix(u_inner_radius, 1.0, 0.4), mix(u_inner_radius, 1.0, 0.6), n0);
    float d0 = distance(uv, r0 / max(len, 1e-5) * uv);
    float v0 = light1(1.0, 10.0, d0);
    // safe inversion of smoothstep(r0*1.05, r0, len) — edge0 > edge1 is undefined in GLSL 330
    v0 *= 1.0 - smoothstep(r0, r0 * 1.05, len);
    float cl = cos(ang + u_t * 2.0) * 0.5 + 0.5;

    // highlight
    float a   = u_t * -1.0;
    vec2  pos = vec2(cos(a), sin(a)) * r0;
    float d   = distance(uv, pos);
    float v1  = light2(1.5, 5.0, d);
    v1 *= light1(1.0, 50.0, d0);

    // outer falloff — safe inversion of smoothstep(1.0, inner, len) — edge0 > edge1 is undefined
    float v2 = 1.0 - smoothstep(mix(u_inner_radius, 1.0, n0 * 0.5), 1.0, len);

    // center hole
    float v3 = smoothstep(u_inner_radius, mix(u_inner_radius, 1.0, 0.5), len);

    // color
    vec3 col = mix(u_color1, u_color2, cl);
    col = mix(u_color3, col, v0);
    col = (col + v1) * v2 * v3;
    col = clamp(col, 0.0, 1.0);

    vec4 extracted = extractAlpha(col);
    float out_a = extracted.a * u_opacity;
    frag_color = vec4(extracted.rgb * out_a, out_a);
}
"""

_QUAD = np.array([-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0], dtype="f4")

# Keep a faint ring during quiet sections while still breathing with amplitude.
_OPACITY_FLOOR = 0.22


def _normalize_channel(raw: np.ndarray) -> np.ndarray:
    if raw.size == 0:
        return raw
    lo, hi = np.percentile(raw, (5.0, 95.0))
    span = max(float(hi - lo), 1e-6)
    return np.clip((raw - lo) / span, 0.0, 1.0).astype(np.float32)


class PlasmaRingGL(AudioVisualMixin, ClipGL):
    """Noise-displaced plasma ring; bass contracts the ring inward, amplitude drives opacity."""

    clip_type: ClassVar[str] = "std-plasma-ring-gl"
    clip_category: ClassVar[ClipCategory] = ClipCategory.AUDIO
    clip_tags: ClassVar[list[str]] = [ClipTag.AUDIO_REACTIVE, ClipTag.ANIMATED, ClipTag.GL]

    color_primary: ColorToken | Color = color_field(ColorToken.PRIMARY)
    color_secondary: ColorToken | Color = color_field(ColorToken.SECONDARY)
    color_background: ColorToken | Color = color_field(ColorToken.BACKGROUND)
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
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    inner_radius: float = Field(
        default=0.6,
        ge=0.1,
        le=0.9,
        multiple_of=0.1,
        description="Base inner radius; smaller = thicker ring torus",
    )
    noise_scale: float = Field(
        default=0.65,
        ge=0.1,
        le=2.0,
        multiple_of=0.05,
        description="Noise frequency — lower = smooth blobs, higher = chaotic turbulence",
    )
    speed: float = Field(
        default=1.0,
        ge=0.1,
        le=3.0,
        multiple_of=0.1,
        description="Animation speed multiplier",
    )
    bass_pulse: float = Field(
        default=0.35,
        ge=0.0,
        le=1.0,
        multiple_of=0.05,
        description="Amount bass energy contracts the ring inward (0 = no pulse)",
    )
    sensitivity: float = Field(
        default=2.5,
        ge=0.1,
        le=8.0,
        multiple_of=0.1,
        description="Audio response gain on bass pulse and amplitude-driven opacity",
    )
    smoothing: float = Field(
        default=0.45,
        ge=0.0,
        le=0.9,
        multiple_of=0.05,
        description="EMA smoothing applied to audio data (0 = raw, 0.9 = very sluggish)",
    )

    _canvas_h: float = PrivateAttr(default=0.0)
    _bounds_x: float = PrivateAttr(default=0.0)
    _bounds_y: float = PrivateAttr(default=0.0)
    _bounds_w: float = PrivateAttr(default=0.0)
    _bounds_h: float = PrivateAttr(default=0.0)

    _program: moderngl.Program | None = PrivateAttr(default=None)
    _vao: moderngl.VertexArray | None = PrivateAttr(default=None)

    # Pre-computed per-frame EMA-smoothed, job-normalized audio drive.
    _bass_history: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype="f4"))
    _amp_history: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype="f4"))

    async def prepare(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        b = bounds or Rect(0, 0, ctx.job.width, ctx.job.height)
        self._canvas_h = float(ctx.job.height)
        self._bounds_x = float(b.x)
        self._bounds_y = float(b.y)
        self._bounds_w = float(b.width)
        self._bounds_h = float(b.height)
        self._bass_history, self._amp_history = self._precompute_audio(ctx)

    def _precompute_audio(self, ctx: PrepareContext) -> tuple[np.ndarray, np.ndarray]:
        total = max(ctx.job.total_frames, 0)
        bass_history = np.zeros(total, dtype="f4")
        amp_history = np.zeros(total, dtype="f4")
        if total == 0:
            return bass_history, amp_history

        frames: list[AudioBusFrame] | None = self.bus_timeline(ctx)
        if not frames:
            return bass_history, amp_history

        n_bus = min(total, len(frames))
        bass_norm = _normalize_channel(
            np.asarray([float(frames[f].bass) for f in range(n_bus)], dtype=np.float32)
        )
        amp_norm = _normalize_channel(
            np.asarray([float(frames[f].amplitude) for f in range(n_bus)], dtype=np.float32)
        )

        s = float(self.smoothing)
        one_minus_s = 1.0 - s
        sens = float(self.sensitivity)
        bass_acc = 0.0
        amp_acc = 0.0
        for f in range(total):
            if f >= n_bus:
                bass_acc *= s
                amp_acc *= s
            else:
                bass_acc = bass_acc * s + float(bass_norm[f]) * one_minus_s
                amp_acc = amp_acc * s + float(amp_norm[f]) * one_minus_s
            bass_history[f] = min(1.0, bass_acc * sens)
            amp_history[f] = min(1.0, amp_acc * sens)
        return bass_history, amp_history

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

        if self._bass_history.shape[0] > 0:
            f = max(0, min(ctx.time.frame, self._bass_history.shape[0] - 1))
            bass_val = float(self._bass_history[f])
            amp_val = float(self._amp_history[f]) if self._amp_history.size else 0.0
        else:
            af = ctx.audio_bus_frame
            bass_val = min(1.0, float(np.clip(af.bass, 0.0, 1.0)) * float(self.sensitivity))
            amp_val = min(1.0, float(np.clip(af.amplitude, 0.0, 1.0)) * float(self.sensitivity))

        radius = max(0.05, self.inner_radius - bass_val * self.bass_pulse)
        opacity_out = self.opacity * (_OPACITY_FLOOR + (1.0 - _OPACITY_FLOOR) * amp_val)

        r1, g1, b1, _ = resolve_color(self.color_primary, ctx.job.colors).rgba
        r2, g2, b2, _ = resolve_color(self.color_secondary, ctx.job.colors).rgba
        r3, g3, b3, _ = resolve_color(self.color_background, ctx.job.colors).rgba

        self._set_uniform(prog, "u_res", (self._bounds_w, self._bounds_h))
        self._set_uniform(prog, "u_origin", (self._bounds_x, self._bounds_y))
        self._set_uniform(prog, "u_canvas_h", self._canvas_h)
        self._set_uniform(prog, "u_t", ctx.time.t * self.speed)
        self._set_uniform(prog, "u_inner_radius", radius)
        self._set_uniform(prog, "u_noise_scale", self.noise_scale)
        self._set_uniform(prog, "u_opacity", opacity_out)
        self._set_uniform(prog, "u_color1", (r1, g1, b1))
        self._set_uniform(prog, "u_color2", (r2, g2, b2))
        self._set_uniform(prog, "u_color3", (r3, g3, b3))
        self._set_uniform(prog, "u_offset_x", self.offset_x)
        self._set_uniform(prog, "u_offset_y", self.offset_y)

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
