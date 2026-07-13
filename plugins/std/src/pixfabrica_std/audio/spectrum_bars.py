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
uniform float u_bar_heights[128];
uniform float u_half;
uniform vec3  u_color_left;
uniform vec3  u_color_right;
uniform vec3  u_color_peak;
uniform float u_bar_fade;
uniform float u_bar_gap_ratio;
uniform float u_max_bar_height;
uniform float u_glow_intensity;
uniform float u_reflection_alpha;
uniform float u_rounded_top;
uniform float u_offset_y;
uniform float u_bar_count_f;
uniform float u_color_blend;

out vec4 frag_color;

// Vertical capsule (pill) SDF — a and b are the inner segment endpoints, r is radius
float capsule_sdf(vec2 p, vec2 a, vec2 b, float r) {
    vec2 pa = p - a, ba = b - a;
    float h = clamp(dot(pa, ba) / dot(ba, ba), 0.0, 1.0);
    return length(pa - ba * h) - r;
}

void main() {
    // Local pixel coords: (0,0) = top-left of bounds, x right, y down
    float px = gl_FragCoord.x - u_origin.x;
    float py = (u_canvas_h - gl_FragCoord.y) - u_origin.y;

    float W = u_res.x;
    float H = u_res.y;

    float baseline_y = u_offset_y * H;
    float slot_w     = W / u_bar_count_f;
    float half_w     = slot_w * (1.0 - u_bar_gap_ratio) * 0.5;

    // Glow spread in pixels: wider at higher intensity, minimum 1px so bars are always visible
    float glow_spread = max(half_w * u_glow_intensity * 3.0 + 1.0, 1.0);

    vec3  color_acc = vec3(0.0);
    float alpha_acc = 0.0;

    for (int i = 0; i < 128; i++) {
        if (float(i) >= u_bar_count_f) break;
        float bar_h = u_bar_heights[i] * u_max_bar_height * H;
        if (bar_h < 0.5) continue;

        float cx      = (float(i) + 0.5) * slot_w;
        float top_y   = baseline_y - bar_h;

        // Clamp pill radius so very short bars still look correct
        float inner_r = min(half_w, bar_h * 0.5);
        vec2  cap_a   = vec2(cx, top_y + inner_r);
        vec2  cap_b   = vec2(cx, baseline_y - inner_r);

        float sdf;
        if (u_rounded_top > 0.5) {
            sdf = capsule_sdf(vec2(px, py), cap_a, cap_b, inner_r);
        } else {
            vec2 bar_ctr = vec2(cx, (top_y + baseline_y) * 0.5);
            vec2 bar_hs  = vec2(half_w, bar_h * 0.5);
            vec2 d       = abs(vec2(px, py) - bar_ctr) - bar_hs;
            sdf = length(max(d, 0.0)) + min(max(d.x, d.y), 0.0);
        }

        vec3 bar_color;
        if (u_color_blend > 0.5) {
            float denom = max(u_half - 1.0, 1.0);
            if (float(i) < u_half) {
                bar_color = mix(u_color_left, u_color_right, float(i) / denom);
            } else {
                bar_color = mix(u_color_right, u_color_left, (u_bar_count_f - 1.0 - float(i)) / denom);
            }
        } else {
            bar_color = (float(i) < u_half) ? u_color_left : u_color_right;
        }

        // t: 0 at baseline, 1 at bar top — fade applies to both color and alpha
        float t     = clamp((baseline_y - py) / max(bar_h, 0.001), 0.0, 1.0);
        bar_color   = mix(bar_color, u_color_peak, t * t);
        float fade  = mix(u_bar_fade, 1.0, t);

        float glow_factor = exp(-max(sdf, 0.0) / glow_spread);
        float is_inside   = step(sdf, 0.0);
        float contrib     = max(is_inside, glow_factor * u_glow_intensity) * fade;

        vec3 lit = bar_color * contrib;
        color_acc = max(color_acc, lit);
        alpha_acc = max(alpha_acc, contrib);

        // Floor reflection — only below baseline
        if (py > baseline_y) {
            float ref_depth = py - baseline_y;
            float ref_fade  = max(1.0 - ref_depth / max(bar_h, 1.0), 0.0);
            if (ref_fade > 0.001) {
                // Mirror the pixel vertically around the baseline
                float ref_py  = 2.0 * baseline_y - py;
                float ref_sdf = capsule_sdf(vec2(px, ref_py), cap_a, cap_b, inner_r);
                float ref_in  = step(ref_sdf, 0.0);
                float ref_a   = ref_in * ref_fade * u_reflection_alpha;

                // Mirrored brightness: at baseline reflection = bottom of bar (dark)
                float ref_t  = clamp((baseline_y - ref_py) / max(bar_h, 0.001), 0.0, 1.0);
                float ref_br = mix(u_bar_fade, 1.0, ref_t);

                vec3 ref_lit = bar_color * ref_br * ref_a;
                color_acc = max(color_acc, ref_lit);
                alpha_acc = max(alpha_acc, ref_a);
            }
        }
    }

    // Premultiplied alpha output
    frag_color = vec4(color_acc * alpha_acc, alpha_acc);
}
"""

_QUAD = np.array([-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0], dtype="f4")

# Outer bars (left/right flanks) stay hot; center-adjacent bars stay quieter.
_EDGE_CENTER_FLOOR = 0.12
_EDGE_FOCUS_POWER = 1.85
# Leave headroom before gain so high sensitivity does not flatline bars at 1.0.
_FRAME_HEADROOM = 0.92
_SHAPE_COMPRESS = 1.12
_ROBUST_PEAK_PCT = 88.0
_SAT_GAIN = 0.44


def _edge_envelope(half: int) -> np.ndarray:
    """Symmetric weighting: index 0 = outermost bar, index half-1 = center-adjacent."""
    if half <= 1:
        return np.ones(max(half, 1), dtype=np.float32)
    t = np.arange(half, dtype=np.float32) / float(half - 1)
    return (
        _EDGE_CENTER_FLOOR + (1.0 - _EDGE_CENTER_FLOOR) * np.power(1.0 - t, _EDGE_FOCUS_POWER)
    ).astype(np.float32)


def _normalize_amplitudes(frames: list[AudioBusFrame], n_bus: int) -> np.ndarray:
    if n_bus <= 0:
        return np.zeros(0, dtype=np.float32)
    raw = np.asarray([float(frames[f].amplitude) for f in range(n_bus)], dtype=np.float32)
    lo, hi = np.percentile(raw, (5.0, 95.0))
    span = max(float(hi - lo), 1e-6)
    return np.clip((raw - lo) / span, 0.0, 1.0).astype(np.float32)


def _spatial_smooth_half(row: np.ndarray) -> np.ndarray:
    """Light neighbor blend so adjacent bars move together, not independently."""
    if row.size < 3:
        return row
    out = row.copy()
    out[0] = row[0] * 0.62 + row[1] * 0.38
    out[-1] = row[-2] * 0.38 + row[-1] * 0.62
    out[1:-1] = row[:-2] * 0.12 + row[1:-1] * 0.76 + row[2:] * 0.12
    return out


def _soft_saturate(row: np.ndarray, gain: float) -> np.ndarray:
    """Smooth ceiling — bars approach full height but rarely pin flat at 1.0."""
    if gain <= 1e-8:
        return np.zeros_like(row)
    return np.tanh(row * gain * _SAT_GAIN).astype(np.float32)


def _shape_half_row(
    smoothed_row: np.ndarray,
    envelope: np.ndarray,
    drive: float,
    sensitivity: float,
) -> np.ndarray:
    peak = float(np.percentile(smoothed_row, _ROBUST_PEAK_PCT))
    if peak <= 1e-8:
        return np.zeros_like(smoothed_row)
    shape = np.power(np.clip(smoothed_row / peak, 0.0, 1.0), _SHAPE_COMPRESS)
    row = _spatial_smooth_half(shape * envelope)
    mx = float(row.max())
    if mx > 1e-8:
        row = row * (_FRAME_HEADROOM / mx)
    return _soft_saturate(row, drive * sensitivity)


class SpectrumBars(AudioVisualMixin, ClipGL):
    """Symmetrical discrete bar-style audio spectrum visualiser with neon glow and floor reflection."""

    clip_type: ClassVar[str] = "std-spectrum-bars"
    clip_category: ClassVar[ClipCategory] = ClipCategory.AUDIO
    clip_tags: ClassVar[list[str]] = [
        ClipTag.AUDIO_REACTIVE,
        ClipTag.ANIMATED,
        ClipTag.GL,
        ClipTag.GLOW,
    ]

    bar_count: int = Field(
        default=32,
        ge=4,
        le=64,
        multiple_of=1,
        description="Number of bars (even; odd values are rounded up). Left and right halves mirror each other.",
    )
    color_left: ColorToken | Color = color_field(ColorToken.SECONDARY)
    color_right: ColorToken | Color = color_field(ColorToken.PRIMARY)
    color_peak: ColorToken | Color = color_field(ColorToken.ACCENT)
    offset_y: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Baseline vertical position as a fraction of bounds height (0=top, 1=bottom).",
    )
    bar_fade: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Vertical fade per bar affecting both color and alpha (1.0 = fully opaque, 0.0 = transparent at baseline).",
    )
    bar_gap_ratio: float = Field(
        default=0.2,
        ge=0.0,
        le=0.8,
        multiple_of=0.1,
        description="Fraction of each bar slot taken by the gap between bars.",
    )
    max_bar_height: float = Field(
        default=0.45,
        ge=0.1,
        le=1.0,
        multiple_of=0.1,
        description="Maximum bar height as a fraction of the clip bounds height.",
    )
    smoothing: float = Field(
        default=0.5,
        ge=0.0,
        le=0.9,
        multiple_of=0.05,
        description="Temporal smoothing applied to bar heights each frame (0=raw, 0.9=sluggish).",
    )
    rounded_top: bool = Field(
        default=True,
        description="Pill-shaped cap on bar tops when true; flat rectangular top when false.",
    )
    bin_start: int = Field(
        default=5,
        ge=0,
        le=56,
        multiple_of=1,
        description="First log band mapped to the outermost bar. Raise to skip sub-bass dead zones; lower for more low-end.",
    )
    glow_intensity: float = Field(
        default=0.4,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Neon bloom spread around each bar (0=crisp edges, 1=wide glow).",
    )
    reflection_alpha: float = Field(
        default=0.25,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Opacity of the downward floor reflection beneath the baseline (0=off).",
    )
    color_blend: bool = Field(
        default=False,
        description="Blend each half toward the opposite color at the center (outer edge = own color, center = opposite color).",
    )
    sensitivity: float = Field(
        default=2.5,
        ge=0.1,
        le=8.0,
        multiple_of=0.05,
        description="Audio response gain on bar heights after job-wide normalization",
    )

    _canvas_h: float = PrivateAttr(default=0.0)
    _bounds_x: float = PrivateAttr(default=0.0)
    _bounds_y: float = PrivateAttr(default=0.0)
    _bounds_w: float = PrivateAttr(default=0.0)
    _bounds_h: float = PrivateAttr(default=0.0)

    _program: moderngl.Program | None = PrivateAttr(default=None)
    _vao: moderngl.VertexArray | None = PrivateAttr(default=None)

    # Pre-computed per-frame smoothed bar heights: shape (total_frames, 128).
    # Only the first ``bar_count`` slots per row are active. Computed in
    # prepare() so draw() stays stateless under parallel rendering.
    _bar_history: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros((0, 128), dtype="f4"))

    @field_validator("bar_count", mode="after")
    @classmethod
    def _coerce_even(cls, v: int) -> int:
        return v if v % 2 == 0 else min(v + 1, 128)

    async def prepare(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        b = bounds or Rect(0, 0, ctx.job.width, ctx.job.height)
        self._canvas_h = float(ctx.job.height)
        self._bounds_x = float(b.x)
        self._bounds_y = float(b.y)
        self._bounds_w = float(b.width)
        self._bounds_h = float(b.height)
        self._bar_history = self._precompute_bar_history(ctx)

    def _precompute_bar_history(self, ctx: PrepareContext) -> np.ndarray:
        """Roll the EMA smoother over the whole job timeline so draw() can do a
        constant-time lookup. Returns a (total_frames, 128) f4 array; unused
        slots beyond ``bar_count`` stay zero."""
        total = max(ctx.job.total_frames, 0)
        history = np.zeros((total, 128), dtype="f4")
        if total == 0:
            return history

        frames: list[AudioBusFrame] | None = self.bus_timeline(ctx)
        if not frames:
            return history  # no audio bus → bars stay flat

        n = self.bar_count
        half = n // 2
        bin_start = self.bin_start
        # Pre-compute per-bar bin index + gain; same formula as the original draw()
        bin_idxs = np.empty(half, dtype=np.int64)
        for i in range(half):
            t = i / max(half - 1, 1)
            bin_idxs[i] = round(bin_start + t * (N_SPECTRUM - 1 - bin_start))

        envelope = _edge_envelope(half)

        s = float(self.smoothing)
        one_minus_s = 1.0 - s
        sens = float(self.sensitivity)
        n_bus = min(total, len(frames))
        amp_norm = _normalize_amplitudes(frames, n_bus)
        smoothed = np.zeros((total, half), dtype="f4")
        drive = np.zeros(total, dtype="f4")
        prev = np.zeros(half, dtype="f4")
        drive_state = 0.0
        for f in range(total):
            if f >= n_bus:
                prev = prev * s
                drive_state = drive_state * s
            else:
                freq = np.asarray(frames[f].spectrum, dtype="f4")
                prev = prev * s + freq[bin_idxs] * one_minus_s
                drive_state = drive_state * s + float(amp_norm[f]) * one_minus_s
            smoothed[f] = prev
            drive[f] = drive_state

        for f in range(total):
            row = _shape_half_row(smoothed[f], envelope, float(drive[f]), sens)
            history[f, :half] = row
            history[f, n - half : n] = row[::-1]
        return history

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
        n = self.bar_count

        # Stateless lookup: the EMA was pre-computed in prepare().
        if self._bar_history.shape[0] > 0:
            f = max(0, min(ctx.time.frame, self._bar_history.shape[0] - 1))
            bar_heights = self._bar_history[f]
        else:
            half = n // 2
            bin_start = self.bin_start
            bin_idxs = np.empty(half, dtype=np.int64)
            for i in range(half):
                t = i / max(half - 1, 1)
                bin_idxs[i] = round(bin_start + t * (N_SPECTRUM - 1 - bin_start))
            envelope = _edge_envelope(half)
            af = ctx.audio_bus_frame
            freq = np.asarray(af.spectrum, dtype="f4")
            drive = float(np.clip(af.amplitude, 0.0, 1.0))
            row = _shape_half_row(freq[bin_idxs], envelope, drive, float(self.sensitivity))
            bar_heights = np.zeros(128, dtype="f4")
            bar_heights[:half] = row
            bar_heights[n - half : n] = row[::-1]

        lr, lg, lb, _ = resolve_color(self.color_left, ctx.job.colors).rgba
        rr, rg, rb, _ = resolve_color(self.color_right, ctx.job.colors).rgba
        pr, pg, pb, _ = resolve_color(self.color_peak, ctx.job.colors).rgba

        self._set_uniform(prog, "u_res", (self._bounds_w, self._bounds_h))
        self._set_uniform(prog, "u_origin", (self._bounds_x, self._bounds_y))
        self._set_uniform(prog, "u_canvas_h", self._canvas_h)
        self._set_uniform(prog, "u_bar_count_f", float(n))
        self._set_uniform(prog, "u_half", float(n // 2))
        self._set_uniform(prog, "u_color_left", (lr, lg, lb))
        self._set_uniform(prog, "u_color_right", (rr, rg, rb))
        self._set_uniform(prog, "u_color_peak", (pr, pg, pb))
        self._set_uniform(prog, "u_bar_fade", self.bar_fade)
        self._set_uniform(prog, "u_bar_gap_ratio", self.bar_gap_ratio)
        self._set_uniform(prog, "u_max_bar_height", self.max_bar_height)
        self._set_uniform(prog, "u_glow_intensity", self.glow_intensity)
        self._set_uniform(prog, "u_reflection_alpha", self.reflection_alpha)
        self._set_uniform(prog, "u_rounded_top", 1.0 if self.rounded_top else 0.0)
        self._set_uniform(prog, "u_offset_y", self.offset_y)
        self._set_uniform(prog, "u_color_blend", 1.0 if self.color_blend else 0.0)

        # Set the full float array in one assignment — avoids per-element driver quirks
        if "u_bar_heights[0]" in prog:  # array access: individual float elements
            for i in range(n):
                self._set_uniform(prog, f"u_bar_heights[{i}]", float(bar_heights[i]))
        elif "u_bar_heights" in prog:  # whole-array access (some drivers)
            member = prog["u_bar_heights"]
            if isinstance(member, moderngl.Uniform):
                member.value = tuple(bar_heights.tolist())  # type: ignore[assignment]

        bnd = ctx.bounds
        gl.scissor = (
            int(self._bounds_x),
            int(ctx.job.height - self._bounds_y - bnd.height),
            int(self._bounds_w),
            int(bnd.height),
        )

        assert self._vao is not None
        self._vao.render(moderngl.TRIANGLES)

        gl.scissor = None
