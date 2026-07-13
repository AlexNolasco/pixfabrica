from __future__ import annotations

from typing import Any, ClassVar

import moderngl
import numpy as np
from pydantic import Field, PrivateAttr, field_validator

from pixfabrica_core.audio.bus import N_SPECTRUM, AudioBusFrame
from pixfabrica_core.audio.mixin import AudioVisualMixin
from pixfabrica_core.clips import ClipCategory, ClipGL, ClipTag, PrepareContext, RenderContext
from pixfabrica_core.graphics import Rect
from pixfabrica_core.theme.color import Color, ColorToken, color_field, resolve_color
from pixfabrica_std.tilt import ANGLE_FULL_DESC, ANGLE_FULL_MAX, ANGLE_FULL_MIN

_MAX_BARS = 64

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

uniform float u_offset_y;
uniform float u_strip_w;
uniform float u_strip_left;
uniform float u_angle;
uniform float u_max_bar_height;
uniform float u_bar_count_f;
uniform float u_curve_smooth;

uniform float u_bar_heights[64];
uniform vec3  u_color;

out vec4 frag_color;

// Quadratic B-spline basis (degree 2), scalar x in [0, 1].
vec3 B2_weights(float x) {
    float t = 3.0 * x;
    float b0 = step(0.0, t) * step(t, 1.0);
    float b1 = step(1.0, t) * step(t, 2.0);
    float b2 = step(2.0, t) * step(t, 3.0);
    return 0.5 * vec3(
        b0 * t * t,
        b1 * (-2.0 * t * t + 6.0 * t - 3.0),
        b2 * (3.0 - t) * (3.0 - t)
    );
}

float extendedSymmetricHeight(int i) {
    int half = int(u_bar_count_f) / 2;
    if (i < 0 || i > half) {
        return 0.0;
    }
    if (i == half) {
        return 0.0;
    }
    return u_bar_heights[i];
}

float sampleSymmetricWaveHeight(float rx, float half_strip) {
    int half = int(u_bar_count_f) / 2;
    if (half <= 1) {
        return 0.0;
    }

    // Strip x in [0, 1]; mirror like abs(2*x - 1) in the reference shader.
    float x = (rx + half_strip) / (half_strip * 2.0);
    float sym = abs(2.0 * x - 1.0);
    if (sym >= 1.0) {
        return 0.0;
    }

    float u = sym * float(half - 1);
    int i0 = int(floor(u));
    float local = u - float(i0);
    i0 = clamp(i0, 0, half - 2);

    float h0 = extendedSymmetricHeight(i0 - 1);
    float h1 = extendedSymmetricHeight(i0);
    float h2 = extendedSymmetricHeight(i0 + 1);
    float h_linear = mix(h1, h2, local);

    vec3 w = B2_weights(local);
    float h_b2 = w.x * h0 + w.y * h1 + w.z * h2;

    float blend = clamp(u_curve_smooth * 2.0, 0.0, 1.0);
    return mix(h_linear, h_b2, blend);
}

void main() {
    float px = gl_FragCoord.x - u_origin.x;
    float py = (u_canvas_h - gl_FragCoord.y) - u_origin.y;
    float baseline_y = u_res.y * u_offset_y;

    float sx = px - u_strip_left;
    float sy = baseline_y - py;

    float half_strip = u_strip_w * 0.5;
    float lx = sx - half_strip;
    float ly = sy;

    float a = radians(u_angle);
    float cos_a = cos(a);
    float sin_a = sin(a);
    vec2 r = vec2(lx * cos_a - ly * sin_a, lx * sin_a + ly * cos_a);

    float wave_h = sampleSymmetricWaveHeight(r.x, half_strip) * u_max_bar_height * u_res.y;
    if (wave_h < 0.5 || r.y < 0.0) {
        frag_color = vec4(0.0);
        return;
    }

    float top_dist = wave_h - r.y;
    float alpha = smoothstep(0.0, 1.5, top_dist);
    if (alpha < 0.001) {
        frag_color = vec4(0.0);
        return;
    }

    float crest = clamp(r.y / wave_h, 0.0, 1.0);
    float shade = mix(1.0, 0.78, crest * crest);
    frag_color = vec4(u_color * alpha * shade, alpha);
}
"""

_QUAD = np.array([-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0], dtype="f4")

_PEAK_PCT = 90.0
_HEADROOM = 0.88
_SAT_GAIN = 0.48
_CENTER_FOCUS = 1.25
_PROFILE_SMOOTH = np.array([0.06, 0.10, 0.14, 0.20, 0.20, 0.14, 0.10, 0.06], dtype=np.float32)
_PROFILE_SMOOTH /= _PROFILE_SMOOTH.sum()


def _strip_layout(bounds_w: float, width: float) -> tuple[float, float]:
    """Return (strip_left, strip_w). width=1.0 spans edge-to-edge; narrower widths center-pad."""
    strip_w = bounds_w * width
    strip_left = (bounds_w - strip_w) * 0.5
    return strip_left, strip_w


def _bin_group_ranges(bar_count: int, n_spectrum: int = N_SPECTRUM) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for i in range(bar_count):
        start = i * n_spectrum // bar_count
        end = max(start, (i + 1) * n_spectrum // bar_count - 1)
        ranges.append((start, end))
    return ranges


def _mean_group(freq: np.ndarray, start: int, end: int) -> float:
    if end <= start:
        return float(freq[start])
    return float(freq[start : end + 1].mean())


def _shape_row(row: np.ndarray, sensitivity: float) -> np.ndarray:
    """Map smoothed band levels to wave heights with a soft ceiling (no flat-top pegging)."""
    peak = float(np.percentile(row, _PEAK_PCT))
    if peak <= 1e-8:
        return np.zeros_like(row)
    normalized = row / peak
    shaped = np.tanh(normalized * float(sensitivity) * _SAT_GAIN)
    return (shaped * _HEADROOM).astype(np.float32)


def _fold_to_center_profile(grouped: np.ndarray) -> np.ndarray:
    """Fold a linear spectrum row into a center-first radial profile (index 0 = center)."""
    n = int(grouped.shape[0])
    half = n // 2
    mid = n // 2
    profile = np.zeros(half, dtype=np.float32)
    for d in range(half):
        li = mid - 1 - d
        ri = mid + d
        if li >= 0 and ri < n:
            profile[d] = max(float(grouped[li]), float(grouped[ri]))
        elif li >= 0:
            profile[d] = float(grouped[li])
        else:
            profile[d] = float(grouped[ri])
    return profile


def _smooth_profile(profile: np.ndarray) -> np.ndarray:
    if profile.size < 3:
        return profile
    out = profile
    for _ in range(2):
        out = np.convolve(out, _PROFILE_SMOOTH, mode="same")
    return out.astype(np.float32)


def _shape_symmetric_profile(grouped: np.ndarray, sensitivity: float) -> np.ndarray:
    """Map grouped spectrum to a smooth center-peaked symmetric half-profile."""
    shaped = _shape_row(grouped, sensitivity)
    half = shaped.shape[0] // 2
    if half < 1 or float(shaped.max()) <= 1e-8:
        return np.zeros(half, dtype=np.float32)

    profile = _fold_to_center_profile(shaped)
    t = np.arange(half, dtype=np.float32) / float(max(half - 1, 1))
    center_weight = np.power(1.0 - t, _CENTER_FOCUS).astype(np.float32)
    profile = _smooth_profile(profile * center_weight)

    peak = float(np.percentile(profile, _PEAK_PCT))
    if peak <= 1e-8:
        return np.zeros(half, dtype=np.float32)
    return np.clip(profile / peak * _HEADROOM, 0.0, _HEADROOM).astype(np.float32)


class EqWaveGL(AudioVisualMixin, ClipGL):
    """Symmetrical center-peaked filled audio wave — single color, bus-driven."""

    clip_type: ClassVar[str] = "std-eq-wave-gl"
    clip_category: ClassVar[ClipCategory] = ClipCategory.AUDIO
    clip_tags: ClassVar[list[str]] = [
        ClipTag.AUDIO_REACTIVE,
        ClipTag.ANIMATED,
        ClipTag.GL,
    ]

    bar_count: int = Field(
        default=64,
        ge=16,
        le=_MAX_BARS,
        multiple_of=1,
        description="Number of control points (even; odd values round up). Mirrored left/right from center.",
    )
    max_bar_height: float = Field(
        default=0.15,
        ge=0.05,
        le=1.0,
        multiple_of=0.05,
        description="Maximum wave height as a fraction of the clip bounds height.",
    )
    width: float = Field(
        default=1.0,
        ge=0.05,
        le=1.0,
        multiple_of=0.05,
        description="Strip width as a fraction of the container (1.0 = edge-to-edge).",
    )
    curve_smooth: float = Field(
        default=0.45,
        ge=0.0,
        le=0.5,
        multiple_of=0.05,
        description="B-spline smoothing between bins (0 = linear, 0.5 = soft B-spline curves).",
    )
    color: ColorToken | Color = color_field(ColorToken.PRIMARY)
    offset_y: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Vertical baseline position (0 = top, 1 = bottom); wave grows upward from here.",
    )
    angle: float = Field(
        default=0.0,
        ge=ANGLE_FULL_MIN,
        le=ANGLE_FULL_MAX,
        multiple_of=1.0,
        description=ANGLE_FULL_DESC,
    )
    smoothing: float = Field(
        default=0.45,
        ge=0.0,
        le=0.9,
        multiple_of=0.05,
        description="Temporal smoothing on wave heights (0 = raw, 0.9 = sluggish).",
    )
    sensitivity: float = Field(
        default=5.0,
        ge=0.1,
        le=8.0,
        multiple_of=0.05,
        description="Audio response gain on wave heights after spectrum grouping.",
    )

    _canvas_h: float = PrivateAttr(default=0.0)
    _bounds_x: float = PrivateAttr(default=0.0)
    _bounds_y: float = PrivateAttr(default=0.0)
    _bounds_w: float = PrivateAttr(default=0.0)
    _bounds_h: float = PrivateAttr(default=0.0)

    _program: moderngl.Program | None = PrivateAttr(default=None)
    _vao: moderngl.VertexArray | None = PrivateAttr(default=None)
    _bar_history: np.ndarray = PrivateAttr(
        default_factory=lambda: np.zeros((0, _MAX_BARS // 2), dtype="f4")
    )

    @field_validator("bar_count", mode="before")
    @classmethod
    def _coerce_even(cls, v: object) -> int:
        n = int(v)  # type: ignore[arg-type]
        if n % 2 != 0:
            n = min(n + 1, _MAX_BARS)
        return max(16, min(_MAX_BARS, n))

    async def prepare(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        b = bounds or Rect(0, 0, ctx.job.width, ctx.job.height)
        self._canvas_h = float(ctx.job.height)
        self._bounds_x = float(b.x)
        self._bounds_y = float(b.y)
        self._bounds_w = float(b.width)
        self._bounds_h = float(b.height)
        self._bar_history = self._precompute_bar_history(ctx)

    def _precompute_bar_history(self, ctx: PrepareContext) -> np.ndarray:
        total = max(ctx.job.total_frames, 0)
        half = self.bar_count // 2
        history = np.zeros((total, half), dtype="f4")
        if total == 0:
            return history

        frames: list[AudioBusFrame] | None = self.bus_timeline(ctx)
        if not frames:
            return history

        n = self.bar_count
        ranges = _bin_group_ranges(n)
        s = float(self.smoothing)
        one_minus_s = 1.0 - s
        sens = float(self.sensitivity)
        n_bus = min(total, len(frames))
        prev = np.zeros(n, dtype="f4")

        for f in range(total):
            if f < n_bus:
                freq = np.asarray(frames[f].spectrum, dtype="f4")
                raw = np.array([_mean_group(freq, start, end) for start, end in ranges], dtype="f4")
                prev = prev * s + raw * one_minus_s
            else:
                prev = prev * s
            history[f] = _shape_symmetric_profile(prev, sens)

        return history

    def _set_uniform(self, prog: moderngl.Program, name: str, value: Any) -> None:
        if name in prog:
            member = prog[name]
            if isinstance(member, moderngl.Uniform):
                member.value = value

    def _set_bar_heights(self, prog: moderngl.Program, profile: np.ndarray, n: int) -> None:
        half = n // 2
        if "u_bar_heights[0]" in prog:
            for i in range(half):
                self._set_uniform(prog, f"u_bar_heights[{i}]", float(profile[i]))
            for i in range(half, _MAX_BARS):
                self._set_uniform(prog, f"u_bar_heights[{i}]", 0.0)
        elif "u_bar_heights" in prog:
            member = prog["u_bar_heights"]
            if isinstance(member, moderngl.Uniform):
                padded = tuple(float(profile[i]) if i < half else 0.0 for i in range(_MAX_BARS))
                member.value = padded  # type: ignore[assignment]

    def draw(self, ctx: RenderContext) -> None:
        gl: moderngl.Context = ctx.canvas

        if self._program is None:
            self._program = gl.program(vertex_shader=_VERT, fragment_shader=_FRAG)
            vbo = gl.buffer(_QUAD.tobytes())
            self._vao = gl.simple_vertex_array(self._program, vbo, "in_vert")

        prog = self._program
        n = self.bar_count

        if self._bar_history.shape[0] > 0:
            f_idx = max(0, min(ctx.time.frame, self._bar_history.shape[0] - 1))
            profile = self._bar_history[f_idx]
        else:
            ranges = _bin_group_ranges(n)
            af = ctx.audio_bus_frame
            freq = np.asarray(af.spectrum, dtype="f4")
            raw = np.array([_mean_group(freq, start, end) for start, end in ranges], dtype="f4")
            profile = _shape_symmetric_profile(raw, float(self.sensitivity))

        cr, cg, cb, _ = resolve_color(self.color, ctx.job.colors).rgba

        strip_left, strip_w = _strip_layout(self._bounds_w, float(self.width))

        self._set_uniform(prog, "u_res", (self._bounds_w, self._bounds_h))
        self._set_uniform(prog, "u_origin", (self._bounds_x, self._bounds_y))
        self._set_uniform(prog, "u_canvas_h", self._canvas_h)
        self._set_uniform(prog, "u_strip_w", strip_w)
        self._set_uniform(prog, "u_strip_left", strip_left)
        self._set_uniform(prog, "u_offset_y", self.offset_y)
        self._set_uniform(prog, "u_angle", self.angle)
        self._set_uniform(prog, "u_max_bar_height", self.max_bar_height)
        self._set_uniform(prog, "u_bar_count_f", float(n))
        self._set_uniform(prog, "u_curve_smooth", float(self.curve_smooth))
        self._set_uniform(prog, "u_color", (cr, cg, cb))
        self._set_bar_heights(prog, profile, n)

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
