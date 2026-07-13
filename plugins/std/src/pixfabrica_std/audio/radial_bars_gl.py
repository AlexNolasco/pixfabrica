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

uniform float u_bar_angles[24];
uniform float u_bar_count_f;
uniform float u_sensitivity;
uniform float u_wobble;

uniform vec3  u_color_primary;
uniform float u_has_bg;
uniform vec3  u_color_background;
uniform float u_opacity;

uniform float u_offset_x;
uniform float u_offset_y;
uniform float u_width;

out vec4 frag_color;

#define PI 3.14159265359

void tRotate(inout vec2 p, float a) {
    float s = sin(a), c = cos(a);
    p *= mat2(c, -s, s, c);
}

float sdCircle(vec2 p, float r) { return length(p) - r; }

float opU(float a, float b) { return min(a, b); }
float opS(float a, float b) { return max(a, -b); }

float sdArk(vec2 p, float ir, float or_, float a) {
    float d = sdCircle(p, or_);
    d = opS(d, sdCircle(p, ir));
    tRotate(p, -a * PI / 2.0);
    d = opS(d, -p.y);
    d = opU(d, sdCircle(p - vec2((or_ + ir) / 2.0, 0.0), (or_ - ir) / 2.0));
    return d;
}

void main() {
    float px = gl_FragCoord.x - u_origin.x;
    float py = (u_canvas_h - gl_FragCoord.y) - u_origin.y;

    if (px < 0.0 || px >= u_res.x || py < 0.0 || py >= u_res.y) discard;

    // Square-normalized UV: radius 1 = half of effective diameter (width-based, height-clamped)
    float target_d = u_width * u_res.x;
    float effective_d = min(target_d, u_res.y);
    float norm = max(effective_d * 0.5, 1.0);

    float cx = u_res.x * u_offset_x;
    float cy = u_res.y * u_offset_y;

    vec2 uv = (vec2(px, py) - vec2(cx, cy)) / norm;
    uv.y = -uv.y;

    // Outer ring, inner hole, center dot
    float d = sdCircle(uv, 1.0);
    d = opS(d, sdCircle(uv, 0.34));
    d = opU(d, sdCircle(uv, 0.04));

    float barsStart = 0.37;
    float barsEnd   = 0.94;
    float barId = floor((length(uv) - barsStart) / (barsEnd - barsStart) * u_bar_count_f);

    if (barId >= 0.0 && barId < u_bar_count_f) {
        float barWidth = (barsEnd - barsStart) / u_bar_count_f;
        float barStart = barsStart + barWidth * (barId + 0.25);
        float barAngel = clamp(u_bar_angles[int(barId)] * 0.5, 0.0, 0.5);

        tRotate(uv, -barAngel * u_wobble * sin(barId + u_t));
        uv = abs(uv);

        d = opS(d, sdArk(uv, barStart, barStart + barWidth * 0.5, barAngel));
    }

    float w      = min(fwidth(d), 0.01);
    float inside = 1.0 - smoothstep(-w, w, d);

    if (u_has_bg > 0.5) {
        vec3 c = mix(u_color_background, u_color_primary, inside);
        frag_color = vec4(c * u_opacity, u_opacity);
    } else {
        float alpha = inside * u_opacity;
        frag_color = vec4(u_color_primary * alpha, alpha);
    }
}
"""

_QUAD = np.array(
    [-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0],
    dtype="f4",
)

_MAX_RINGS = 24
_SPECTRUM_CURVE = 0.55
_SAT_GAIN = 0.44
_ANGLE_FLOOR = 0.06  # minimum arc sweep when the bus is connected


def _normalize_columns(raw: np.ndarray, n_bus: int) -> np.ndarray:
    """Stretch each ring column to ~0..1 using robust job-wide percentiles."""
    if raw.size == 0 or n_bus <= 0:
        return raw
    out = raw.copy()
    ref = raw[:n_bus]
    for col in range(ref.shape[1]):
        channel = ref[:, col]
        lo, hi = np.percentile(channel, (5.0, 95.0))
        span = max(float(hi - lo), 1e-6)
        out[:, col] = np.clip((raw[:, col] - lo) / span, 0.0, 1.0)
    return out


def _normalize_amplitudes(frames: list[AudioBusFrame], n_bus: int) -> np.ndarray:
    if n_bus <= 0:
        return np.zeros(0, dtype=np.float32)
    raw = np.asarray([float(frames[f].amplitude) for f in range(n_bus)], dtype=np.float32)
    lo, hi = np.percentile(raw, (5.0, 95.0))
    span = max(float(hi - lo), 1e-6)
    return np.clip((raw - lo) / span, 0.0, 1.0).astype(np.float32)


def _soft_saturate(values: np.ndarray, gain: float) -> np.ndarray:
    if gain <= 1e-8:
        return np.zeros_like(values)
    return np.tanh(values * gain * _SAT_GAIN).astype(np.float32)


def _shape_ring_drives(normalized_row: np.ndarray, drive: float, sensitivity: float) -> np.ndarray:
    floor = _ANGLE_FLOOR
    shaped = _soft_saturate(normalized_row, drive * sensitivity)
    return floor + (1.0 - floor) * shaped


class RadialBarsGL(AudioVisualMixin, ClipGL):
    """Concentric arc rings driven by audio — each ring sweeps open proportional to its frequency band."""

    clip_type: ClassVar[str] = "std-radial-bars-gl"
    clip_category: ClassVar[ClipCategory] = ClipCategory.AUDIO
    clip_tags: ClassVar[list[str]] = [ClipTag.AUDIO_REACTIVE, ClipTag.ANIMATED, ClipTag.GL]

    bar_count: int = Field(
        default=12, ge=4, le=24, multiple_of=1, description="Number of concentric arc rings (4–24)"
    )
    color_primary: ColorToken | Color = color_field(ColorToken.PRIMARY)
    color_background: ColorToken | Color | None = Field(
        default=None,
        description="Background fill color; None = transparent background",
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
    width: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Visual width as a fraction of clip bounds (1.0 = full horizontal span); height clamped to stay in bounds",
    )
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    sensitivity: float = Field(
        default=2.5,
        ge=0.1,
        le=8.0,
        multiple_of=0.1,
        description="Audio response gain on arc sweep after job-wide normalization",
    )
    wobble: float = Field(
        default=0.2,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Per-ring rotation wobble driven by audio and time",
    )
    smoothing: float = Field(
        default=0.45,
        ge=0.0,
        le=0.9,
        multiple_of=0.05,
        description="Temporal EMA smoothing (0 = raw, 0.9 = very sluggish)",
    )
    bin_start: int = Field(
        default=5,
        ge=0,
        le=56,
        multiple_of=1,
        description="First log band mapped to the innermost ring; raise to skip sub-bass",
    )

    _canvas_h: float = PrivateAttr(default=0.0)
    _bounds_x: float = PrivateAttr(default=0.0)
    _bounds_y: float = PrivateAttr(default=0.0)
    _bounds_w: float = PrivateAttr(default=0.0)
    _bounds_h: float = PrivateAttr(default=0.0)

    _program: moderngl.Program | None = PrivateAttr(default=None)
    _vao: moderngl.VertexArray | None = PrivateAttr(default=None)

    # Pre-computed per-frame bar amplitudes: shape (total_frames, 24).
    # barId 0 = innermost (treble), barId n-1 = outermost (bass).
    _bar_history: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros((0, 24), dtype="f4"))

    async def prepare(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        b = bounds or Rect(0, 0, ctx.job.width, ctx.job.height)
        self._canvas_h = float(ctx.job.height)
        self._bounds_x = float(b.x)
        self._bounds_y = float(b.y)
        self._bounds_w = float(b.width)
        self._bounds_h = float(b.height)
        self._bar_history = self._precompute_bar_angles(ctx)

    def _precompute_bar_angles(self, ctx: PrepareContext) -> np.ndarray:
        total = max(ctx.job.total_frames, 0)
        history = np.zeros((total, _MAX_RINGS), dtype="f4")
        if total == 0:
            return history

        frames: list[AudioBusFrame] | None = self.bus_timeline(ctx)
        if not frames:
            return history

        n = self.bar_count
        bin_start = self.bin_start

        bin_idxs = np.empty(n, dtype=np.int64)
        gains = np.empty(n, dtype="f4")
        for i in range(n):
            t = i / max(n - 1, 1)
            bin_idxs[i] = round((N_SPECTRUM - 1) * (1.0 - t) + bin_start * t)
            gains[i] = 0.35 + 0.65 * t

        s = float(self.smoothing)
        one_minus_s = 1.0 - s
        sens = float(self.sensitivity)
        n_bus = min(total, len(frames))
        amp_norm = _normalize_amplitudes(frames, n_bus)
        smoothed = np.zeros((total, n), dtype="f4")
        prev = np.zeros(n, dtype="f4")
        drive_state = 0.0
        drives = np.zeros(total, dtype="f4")
        for f in range(total):
            if f >= n_bus:
                prev = prev * s
                drive_state = drive_state * s
            else:
                freq = np.asarray(frames[f].spectrum, dtype="f4")
                raw = np.power(np.clip(freq[bin_idxs] * gains, 0.0, 1.0), _SPECTRUM_CURVE)
                prev = prev * s + raw * one_minus_s
                drive_state = drive_state * s + float(amp_norm[f]) * one_minus_s
            smoothed[f] = prev
            drives[f] = drive_state

        normalized = _normalize_columns(smoothed[:n_bus], n_bus)
        for f in range(n_bus):
            history[f, :n] = _shape_ring_drives(normalized[f], float(drives[f]), sens)
        for f in range(n_bus, total):
            history[f, :n] = history[f - 1, :n] * s
        return history

    def _set_uniform(self, prog: moderngl.Program, name: str, value: Any) -> None:
        if name in prog:
            member = prog[name]
            if isinstance(member, moderngl.Uniform):
                member.value = value

    def draw(self, ctx: RenderContext) -> None:
        if self.width <= 0.0:
            return

        gl: moderngl.Context = ctx.canvas

        if self._program is None:
            self._program = gl.program(vertex_shader=_VERT, fragment_shader=_FRAG)
            vbo = gl.buffer(_QUAD.tobytes())
            self._vao = gl.simple_vertex_array(self._program, vbo, "in_vert")

        prog = self._program
        n = self.bar_count

        if self._bar_history.shape[0] > 0:
            f = max(0, min(ctx.time.frame, self._bar_history.shape[0] - 1))
            bar_angles = self._bar_history[f]
        else:
            n_rings = self.bar_count
            bin_start = self.bin_start
            bin_idxs = np.empty(n_rings, dtype=np.int64)
            gains = np.empty(n_rings, dtype="f4")
            for i in range(n_rings):
                t = i / max(n_rings - 1, 1)
                bin_idxs[i] = round((N_SPECTRUM - 1) * (1.0 - t) + bin_start * t)
                gains[i] = 0.35 + 0.65 * t
            af = ctx.audio_bus_frame
            freq = np.asarray(af.spectrum, dtype="f4")
            raw = np.power(np.clip(freq[bin_idxs] * gains, 0.0, 1.0), _SPECTRUM_CURVE)
            drive = float(np.clip(af.amplitude, 0.0, 1.0))
            shaped = _shape_ring_drives(raw, drive, float(self.sensitivity))
            bar_angles = np.zeros(_MAX_RINGS, dtype="f4")
            bar_angles[:n_rings] = shaped

        self._set_uniform(prog, "u_res", (self._bounds_w, self._bounds_h))
        self._set_uniform(prog, "u_origin", (self._bounds_x, self._bounds_y))
        self._set_uniform(prog, "u_canvas_h", self._canvas_h)
        self._set_uniform(prog, "u_t", ctx.time.t)

        self._set_uniform(prog, "u_bar_count_f", float(n))
        self._set_uniform(prog, "u_sensitivity", 1.0)
        self._set_uniform(prog, "u_wobble", self.wobble)

        r, g, b, _ = resolve_color(self.color_primary, ctx.job.colors).rgba
        self._set_uniform(prog, "u_color_primary", (r, g, b))

        if self.color_background is not None:
            br, bg_, bb, _ = resolve_color(self.color_background, ctx.job.colors).rgba
            self._set_uniform(prog, "u_has_bg", 1.0)
            self._set_uniform(prog, "u_color_background", (br, bg_, bb))
        else:
            self._set_uniform(prog, "u_has_bg", 0.0)
            self._set_uniform(prog, "u_color_background", (0.0, 0.0, 0.0))

        self._set_uniform(prog, "u_opacity", self.opacity)
        self._set_uniform(prog, "u_offset_x", self.offset_x)
        self._set_uniform(prog, "u_offset_y", self.offset_y)
        self._set_uniform(prog, "u_width", self.width)

        if "u_bar_angles[0]" in prog:
            for i in range(n):
                self._set_uniform(prog, f"u_bar_angles[{i}]", float(bar_angles[i]))
        elif "u_bar_angles" in prog:
            member = prog["u_bar_angles"]
            if isinstance(member, moderngl.Uniform):
                member.value = tuple(float(bar_angles[i]) for i in range(24))

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
