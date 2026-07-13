from __future__ import annotations

from typing import Any, ClassVar

import moderngl
import numpy as np
from pydantic import Field, PrivateAttr

from pixfabrica_core.audio.bus import N_SPECTRUM, AudioBusFrame
from pixfabrica_core.audio.mixin import AudioVisualMixin
from pixfabrica_core.clips import ClipCategory, ClipGL, ClipTag, PrepareContext, RenderContext
from pixfabrica_core.graphics import Rect
from pixfabrica_core.theme.color import Color, ColorToken, color_field, resolve_color
from pixfabrica_std.tilt import ANGLE_BAND_DESC, ANGLE_BAND_MAX, ANGLE_BAND_MIN

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
uniform float u_speed;
uniform float u_wobble;
uniform float u_line_thickness;
uniform float u_opacity;
uniform vec3  u_color_inner;
uniform vec3  u_color_outer;
uniform float u_offset_x;
uniform float u_offset_y;
uniform float u_angle;
uniform float u_luma_alpha;
uniform float u_glow_intensity;
uniform float u_line_amps[6];
uniform float u_bass;

out vec4 frag_color;

vec4 lineLayer(
    vec2 uv,
    float edge_x,
    float speed,
    float height,
    vec3 col,
    float amp,
    float t,
    float wobble,
    float thickness,
    float bass
) {
    float edge = smoothstep(1.0, 0.0, edge_x);
    float drive = clamp(amp, 0.0, 3.0);
    float wave_h = height + drive * 5.0;
    float wave_amp = wobble * (0.15 + drive * 1.25) * (1.0 + bass * 1.5);
    uv.y += edge * sin(t * speed + uv.x * wave_h) * wave_amp;
    float hw = thickness * (1.0 + drive * 0.35);
    float d = abs(uv.y) - hw;
    float core = smoothstep(
        0.06 * smoothstep(0.2, 0.9, edge_x),
        0.0,
        d
    );
    float glow_boost = 1.0 + drive * 0.35;
    float effective_glow = u_glow_intensity * glow_boost;
    float spread = max(hw * glow_boost * u_glow_intensity * 3.0 + 0.001, 0.001);
    float halo = u_glow_intensity > 0.0 ? exp(-max(d, 0.0) / spread) * effective_glow : 0.0;
    float line = max(core, halo);
    return vec4(line * col, 1.0) * smoothstep(1.0, 0.3, edge_x);
}

void main() {
    float px = gl_FragCoord.x - u_origin.x;
    float py = (u_canvas_h - gl_FragCoord.y) - u_origin.y;

    if (px < 0.0 || px >= u_res.x || py < 0.0 || py >= u_res.y) discard;

    float cx = u_res.x * u_offset_x;
    float cy = u_res.y * u_offset_y;
    float norm = max(u_res.y, 1.0);
    vec2 uv = vec2(px - cx, cy - py) / norm;

    float a = radians(-u_angle);
    uv = mat2(cos(a), -sin(a), sin(a), cos(a)) * uv;

    float half_aspect = max(u_res.x / u_res.y * 0.5, 0.001);
    float edge_x = abs(uv.x) / half_aspect;
    float edge_y = abs(uv.y) * 2.0;
    float corner = smoothstep(1.0, 0.35, max(edge_x, edge_y));

    vec4 acc = vec4(0.0);
    for (int i = 0; i < 6; i++) {
        float fi = float(i) / 5.0;
        vec3 col = mix(u_color_inner, u_color_outer, fi);
        acc += lineLayer(
            uv,
            edge_x,
            1.0 + fi + u_line_amps[i] * 0.5,
            4.0 + fi,
            col,
            u_line_amps[i],
            u_t * u_speed,
            u_wobble,
            u_line_thickness,
            u_bass
        );
    }

    acc.rgb = min(acc.rgb * corner, vec3(1.0));
    float luma = dot(acc.rgb, vec3(0.299, 0.587, 0.114));
    float alpha = mix(1.0, clamp(luma, 0.0, 1.0), u_luma_alpha) * u_opacity;
    frag_color = vec4(acc.rgb * u_opacity, alpha);
}
"""

_QUAD = np.array([-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0], dtype="f4")

LINE_COUNT = 6
_SHADER_AMP_MAX = 3.0


def _normalize_columns(raw: np.ndarray) -> np.ndarray:
    """Stretch each line column to ~0..1 using robust job-wide percentiles."""
    if raw.size == 0:
        return raw
    out = np.empty_like(raw)
    for col in range(raw.shape[1]):
        channel = raw[:, col]
        lo, hi = np.percentile(channel, (5.0, 95.0))
        span = max(float(hi - lo), 1e-6)
        out[:, col] = np.clip((channel - lo) / span, 0.0, 1.0)
    return out


def _normalize_bass(raw: np.ndarray) -> np.ndarray:
    if raw.size == 0:
        return raw
    lo, hi = np.percentile(raw, (5.0, 95.0))
    span = max(float(hi - lo), 1e-6)
    return np.clip((raw - lo) / span, 0.0, 1.0).astype(np.float32)


class WavyLinesGL(AudioVisualMixin, ClipGL):
    """Stacked sine wave lines — each layer driven by a log band on the audio bus."""

    clip_type: ClassVar[str] = "std-wavy-lines-gl"
    clip_category: ClassVar[ClipCategory] = ClipCategory.AUDIO
    clip_tags: ClassVar[list[str]] = [ClipTag.AUDIO_REACTIVE, ClipTag.ANIMATED, ClipTag.GL]

    color_inner: ColorToken | Color = color_field(ColorToken.PRIMARY)
    color_outer: ColorToken | Color = color_field(ColorToken.ACCENT)
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
    angle: float = Field(
        default=0.0,
        ge=ANGLE_BAND_MIN,
        le=ANGLE_BAND_MAX,
        multiple_of=1.0,
        description=ANGLE_BAND_DESC,
    )
    opacity: float = Field(default=1.0, ge=0.0, le=1.0, multiple_of=0.1)
    speed: float = Field(
        default=1.0,
        ge=0.1,
        le=4.0,
        multiple_of=0.1,
        description="Animation speed multiplier",
    )
    wobble: float = Field(
        default=0.65,
        ge=0.0,
        le=0.8,
        multiple_of=0.05,
        description="Base vertical wave amplitude",
    )
    sensitivity: float = Field(
        default=4.0,
        ge=0.1,
        le=8.0,
        multiple_of=0.1,
        description="Audio response gain on line drive after job-wide normalization",
    )
    line_thickness: float = Field(
        default=0.004,
        ge=0.001,
        le=0.02,
        multiple_of=0.001,
        description="Line half-thickness in normalized UV space",
    )
    glow_intensity: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Neon bloom spread around each line (0 = crisp edges, 1 = wide glow)",
    )
    smoothing: float = Field(
        default=0.05,
        ge=0.0,
        le=0.9,
        multiple_of=0.05,
        description="Temporal EMA smoothing per line (0 = raw, 0.9 = sluggish)",
    )
    bin_start: int = Field(
        default=5,
        ge=0,
        le=56,
        multiple_of=1,
        description="First spectrum band mapped to the innermost line",
    )
    luma_alpha: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Luma-based transparency (0 = solid, 1 = dark areas transparent)",
    )

    _canvas_h: float = PrivateAttr(default=0.0)
    _bounds_x: float = PrivateAttr(default=0.0)
    _bounds_y: float = PrivateAttr(default=0.0)
    _bounds_w: float = PrivateAttr(default=0.0)
    _bounds_h: float = PrivateAttr(default=0.0)
    _program: moderngl.Program | None = PrivateAttr(default=None)
    _vao: moderngl.VertexArray | None = PrivateAttr(default=None)
    _line_history: np.ndarray = PrivateAttr(
        default_factory=lambda: np.zeros((0, LINE_COUNT), dtype="f4")
    )
    _bass_history: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype="f4"))

    async def prepare(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        b = bounds or Rect(0, 0, ctx.job.width, ctx.job.height)
        self._canvas_h = float(ctx.job.height)
        self._bounds_x = float(b.x)
        self._bounds_y = float(b.y)
        self._bounds_w = float(b.width)
        self._bounds_h = float(b.height)
        self._line_history, self._bass_history = self._precompute_audio_history(ctx)

    def _precompute_audio_history(self, ctx: PrepareContext) -> tuple[np.ndarray, np.ndarray]:
        total = max(ctx.job.total_frames, 0)
        history = np.zeros((total, LINE_COUNT), dtype="f4")
        bass_history = np.zeros(total, dtype="f4")
        if total == 0:
            return history, bass_history

        frames: list[AudioBusFrame] | None = self.bus_timeline(ctx)
        if not frames:
            return history, bass_history

        bin_start = self.bin_start
        bin_idxs = np.empty(LINE_COUNT, dtype=np.int64)
        for i in range(LINE_COUNT):
            t = i / max(LINE_COUNT - 1, 1)
            bin_idxs[i] = round(bin_start + t * (N_SPECTRUM - 1 - bin_start))

        s = float(self.smoothing)
        one_minus_s = 1.0 - s
        sens = float(self.sensitivity)
        n = min(total, len(frames))
        smoothed = np.zeros((n, LINE_COUNT), dtype="f4")
        bass_raw = np.zeros(n, dtype="f4")
        prev = np.zeros(LINE_COUNT, dtype="f4")
        for f in range(n):
            af = frames[f]
            freq = np.asarray(af.spectrum, dtype="f4")
            raw = np.power(np.clip(freq[bin_idxs], 0.0, 1.0), 0.55)
            prev = prev * s + raw * one_minus_s
            smoothed[f] = prev
            bass_raw[f] = float(af.bass)

        normalized = _normalize_columns(smoothed)
        history[:n] = np.clip(normalized * sens, 0.0, _SHADER_AMP_MAX)

        bass_norm = _normalize_bass(bass_raw)
        bass_acc = 0.0
        for f in range(n):
            bass_acc = bass_acc * s + float(bass_norm[f]) * one_minus_s
            bass_history[f] = bass_acc
        for f in range(n, total):
            bass_acc *= s
            bass_history[f] = bass_acc
        return history, bass_history

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

        if self._line_history.shape[0] > 0:
            f = max(0, min(ctx.time.frame, self._line_history.shape[0] - 1))
            line_amps = self._line_history[f]
            bass = float(self._bass_history[f]) if self._bass_history.size else 0.0
        else:
            af = ctx.audio_bus_frame
            freq = np.asarray(af.spectrum, dtype="f4")
            bin_start = self.bin_start
            bin_idxs = np.empty(LINE_COUNT, dtype=np.int64)
            for i in range(LINE_COUNT):
                t = i / max(LINE_COUNT - 1, 1)
                bin_idxs[i] = round(bin_start + t * (N_SPECTRUM - 1 - bin_start))
            raw = np.power(np.clip(freq[bin_idxs], 0.0, 1.0), 0.55)
            line_amps = np.clip(raw * float(self.sensitivity), 0.0, _SHADER_AMP_MAX)
            bass = self.scale_audio(float(af.bass))

        ir, ig, ib, _ = resolve_color(self.color_inner, ctx.job.colors).rgba
        or_, og, ob, _ = resolve_color(self.color_outer, ctx.job.colors).rgba

        self._set_uniform(prog, "u_res", (self._bounds_w, self._bounds_h))
        self._set_uniform(prog, "u_origin", (self._bounds_x, self._bounds_y))
        self._set_uniform(prog, "u_canvas_h", self._canvas_h)
        self._set_uniform(prog, "u_t", float(ctx.time.t))
        self._set_uniform(prog, "u_speed", float(self.speed))
        self._set_uniform(prog, "u_wobble", float(self.wobble))
        self._set_uniform(prog, "u_line_thickness", float(self.line_thickness))
        self._set_uniform(prog, "u_opacity", float(self.opacity))
        self._set_uniform(prog, "u_color_inner", (ir, ig, ib))
        self._set_uniform(prog, "u_color_outer", (or_, og, ob))
        self._set_uniform(prog, "u_offset_x", float(self.offset_x))
        self._set_uniform(prog, "u_offset_y", float(self.offset_y))
        self._set_uniform(prog, "u_angle", float(self.angle))
        self._set_uniform(prog, "u_luma_alpha", float(self.luma_alpha))
        self._set_uniform(prog, "u_glow_intensity", float(self.glow_intensity))
        self._set_uniform(prog, "u_bass", bass)

        if "u_line_amps[0]" in prog:
            for i in range(LINE_COUNT):
                self._set_uniform(prog, f"u_line_amps[{i}]", float(line_amps[i]))

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
