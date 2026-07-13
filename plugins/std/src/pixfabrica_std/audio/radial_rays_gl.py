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
from pixfabrica_std.mesh.shader_helper import precompute_bass_drive
from pixfabrica_std.tilt import ANGLE_FULL_DESC, ANGLE_FULL_MAX, ANGLE_FULL_MIN

# Progress ring radius as a fraction of the ray inner edge (inside); 0.8 = 20% toward center.
_PROGRESS_RING_RADIUS_FRAC = 0.8
# Unfilled track uses the same neon stroke as rays at this gain (filled arc = full intensity).
_PROGRESS_RING_TRACK_GAIN = 0.25

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

uniform float u_ray_count_f;
uniform float u_ray_heights[128];

uniform float u_ray_length;
uniform float u_angle;
uniform float u_offset_x;
uniform float u_offset_y;
uniform float u_width;

uniform vec3  u_color_primary;
uniform vec3  u_color_tip;
uniform float u_glow_intensity;
uniform float u_luma_alpha;
uniform float u_opacity;

uniform float u_scale_factor;
uniform float u_show_progress;
uniform float u_progress;
uniform float u_progress_radius_frac;
uniform float u_progress_track_gain;
uniform vec3  u_progress_color;

out vec4 frag_color;

#define M_PI 3.14159265359

// SDF: vertical capsule from (0, y0) to (0, y1) with cap radius r
float sdCapsuleV(vec2 p, float y0, float y1, float r) {
    float py = clamp(p.y, y0, y1);
    return length(vec2(p.x, p.y - py)) - r;
}

float sdCircle(vec2 p, float r) {
    return length(p) - r;
}

float strokeContrib(float d, float hw_local) {
    float w = fwidth(d);
    float core = 1.0 - smoothstep(-w, w, d);
    float spread = max(hw_local * u_glow_intensity * 3.0 + 0.001, 0.001);
    float glow = exp(-max(d, 0.0) / spread) * u_glow_intensity;
    return max(core, glow);
}

// Progress arc at arc_r with capsule-style round caps (radius hw_local).
float sdProgressArc(vec2 uv, float arc_r, float arc_ang, float hw_local) {
    if (arc_ang <= 0.0001) return 1.0e6;
    float ring_d = abs(length(uv) - arc_r) - hw_local;
    float ang = atan(uv.x, uv.y);
    if (ang < 0.0) ang += 2.0 * M_PI;
    float arc_body = (ang <= arc_ang) ? ring_d : 1.0e6;
    vec2 start_cap = vec2(0.0, arc_r);
    vec2 end_cap = arc_r * vec2(sin(arc_ang), cos(arc_ang));
    float cap_d = min(
        sdCircle(uv - start_cap, hw_local),
        sdCircle(uv - end_cap, hw_local)
    );
    return min(arc_body, cap_d);
}

void main() {
    float px = gl_FragCoord.x - u_origin.x;
    float py = (u_canvas_h - gl_FragCoord.y) - u_origin.y;

    if (px < 0.0 || px >= u_res.x || py < 0.0 || py >= u_res.y) discard;

    float target_d = u_width * u_res.x;
    float effective_d = min(target_d, u_res.y);
    float norm = max(effective_d * 0.5, 1.0);

    float cx = u_res.x * u_offset_x;
    float cy = u_res.y * u_offset_y;

    // Centered normalized UV, Y-up
    vec2 uv = vec2(px - cx, cy - py) / norm;
    uv /= max(u_scale_factor, 0.001);

    // Inner empty radius; ray half-width = arc length per ray slot / 2
    float inside = 1.0 - u_ray_length;
    float hw     = M_PI * inside / (u_ray_count_f * 2.0);

    float best   = 1.0e6;
    float best_t = 0.0;

    for (int i = 0; i < 128; i++) {
        if (float(i) >= u_ray_count_f) break;

        float len = u_ray_heights[i] * u_ray_length;
        if (len < 0.0001) continue;

        // Clockwise layout: ray 0 at top, increasing clockwise
        float a = radians(-u_angle + 360.0 / u_ray_count_f * float(i));
        float s = sin(a), c = cos(a);
        // Rotate uv by -a so this ray's capsule aligns with +Y axis
        vec2 ruv = vec2(uv.x * c + uv.y * s, -uv.x * s + uv.y * c);

        float d = sdCapsuleV(ruv, inside, inside + len, hw);
        if (d < best) {
            best   = d;
            best_t = clamp((ruv.y - inside) / max(len, 0.001), 0.0, 1.0);
        }
    }

    float w          = fwidth(best);
    float inside_fac = 1.0 - smoothstep(-w, w, best);

    float glow_spread = max(hw * u_glow_intensity * 3.0 + 0.001, 0.001);
    float glow_factor = exp(-max(best, 0.0) / glow_spread) * u_glow_intensity;
    float contrib     = max(inside_fac, glow_factor);

    vec3  ray_color = mix(u_color_primary, u_color_tip, best_t * best_t);
    float luma      = dot(ray_color, vec3(0.299, 0.587, 0.114));
    float alpha     = contrib * mix(1.0, clamp(luma, 0.0, 1.0), u_luma_alpha) * u_opacity;
    vec4  final_col = vec4(ray_color * alpha, alpha);

    if (u_show_progress > 0.5) {
        float progress_r = inside * u_progress_radius_frac;
        float ring_d = abs(length(uv) - progress_r) - hw;
        float track_contrib = strokeContrib(ring_d, hw);

        float progress_ang = u_progress * 6.28318530718;
        float fill_d = sdProgressArc(uv, progress_r, progress_ang, hw);
        float fill_contrib = strokeContrib(fill_d, hw);

        if (max(track_contrib, fill_contrib) > 0.001) {
            float ang = atan(uv.x, uv.y);
            if (ang < 0.0) ang += 2.0 * M_PI;
            float ang_t = ang / 6.28318530718;
            vec3 ring_color = mix(u_color_primary, u_progress_color, ang_t * ang_t);
            float luma_ring = dot(ring_color, vec3(0.299, 0.587, 0.114));
            float luma_fac = mix(1.0, clamp(luma_ring, 0.0, 1.0), u_luma_alpha);

            float track_a = track_contrib * luma_fac * u_opacity * u_progress_track_gain;
            float fill_a = fill_contrib * luma_fac * u_opacity;
            vec4 track_col = vec4(ring_color * track_a, track_a);
            vec4 fill_col = vec4(ring_color * fill_a, fill_a);
            final_col = track_col + final_col * (1.0 - track_a);
            final_col = fill_col + final_col * (1.0 - fill_a);
        }
    }

    frag_color = final_col;
}
"""

_QUAD = np.array([-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0], dtype="f4")

# Perceptual lift on log bands before smoothing (matches wavy-lines).
_SPECTRUM_CURVE = 0.55


def _normalize_amplitudes(frames: list[AudioBusFrame], n_bus: int) -> np.ndarray:
    if n_bus <= 0:
        return np.zeros(0, dtype=np.float32)
    raw = np.asarray([float(frames[f].amplitude) for f in range(n_bus)], dtype=np.float32)
    lo, hi = np.percentile(raw, (5.0, 95.0))
    span = max(float(hi - lo), 1e-6)
    return np.clip((raw - lo) / span, 0.0, 1.0).astype(np.float32)


def _circular_smooth(row: np.ndarray) -> np.ndarray:
    """Blend each ray with its neighbors so the ring moves coherently."""
    if row.size < 3:
        return row
    prev = np.roll(row, 1)
    nxt = np.roll(row, -1)
    return (row * 0.76 + prev * 0.12 + nxt * 0.12).astype(np.float32)


def _clip_progress(
    *,
    time_t: float,
    start: float,
    duration: float | None,
    job_duration: float,
) -> float:
    local_t = max(0.0, time_t - start)
    span = max(float(duration if duration is not None else job_duration), 1e-6)
    return min(local_t / span, 1.0)


def _shape_ray_row(
    smoothed_row: np.ndarray,
    drive: float,
    sensitivity: float,
) -> np.ndarray:
    peak = float(smoothed_row.max())
    if peak <= 1e-8:
        return np.zeros_like(smoothed_row)
    shape = smoothed_row / peak
    row = _circular_smooth(shape)
    return np.clip(row * drive * sensitivity, 0.0, 1.0)


class RadialRaysGL(AudioVisualMixin, ClipGL):
    """Circular ray visualizer — capsule bars radiate outward from center, each driven by an audio frequency bin."""

    clip_type: ClassVar[str] = "std-radial-rays-gl"
    clip_category: ClassVar[ClipCategory] = ClipCategory.AUDIO
    clip_tags: ClassVar[list[str]] = [ClipTag.AUDIO_REACTIVE, ClipTag.ANIMATED, ClipTag.GL]

    ray_count: int = Field(
        default=64, ge=8, le=128, description="Number of rays around the circle (8–128)"
    )
    color_primary: ColorToken | Color = color_field(ColorToken.PRIMARY)
    color_tip: ColorToken | Color = color_field(ColorToken.ACCENT)
    glow_intensity: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Neon bloom spread around each ray (0=crisp edges, 1=wide glow)",
    )
    ray_length: float = Field(
        default=0.3,
        ge=0.1,
        le=0.5,
        multiple_of=0.01,
        description="Max ray length as fraction of the layout circle (remainder is the empty inner circle)",
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
    angle: float = Field(
        default=0.0,
        ge=ANGLE_FULL_MIN,
        le=ANGLE_FULL_MAX,
        multiple_of=1.0,
        description=ANGLE_FULL_DESC,
    )
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    smoothing: float = Field(
        default=0.4,
        ge=0.0,
        le=0.90,
        multiple_of=0.05,
        description="Temporal EMA smoothing (0 = raw, 0.9 = very sluggish)",
    )
    sensitivity: float = Field(
        default=2.5,
        ge=0.1,
        le=8.0,
        multiple_of=0.1,
        description="Audio response gain on ray heights after job-wide normalization",
    )
    bin_start: int = Field(
        default=5,
        ge=0,
        le=56,
        multiple_of=1,
        description="First log band mapped to ray 0; raise to skip sub-bass dead zone",
    )
    luma_alpha: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Luminance-based transparency (0 = solid rays, 1 = dark areas transparent)",
    )
    scale_pulse: float = Field(
        default=0.12,
        ge=0.0,
        le=0.25,
        multiple_of=0.01,
        description="Bass-driven uniform scale pulse (0 = off); whole graphic breathes with the bus",
    )
    show_progress: bool = Field(
        default=False,
        description="Draw a thin accent ring at the inner edge that fills over the clip duration",
    )
    progress_color: ColorToken | Color = color_field(ColorToken.ACCENT)

    _canvas_h: float = PrivateAttr(default=0.0)
    _bounds_x: float = PrivateAttr(default=0.0)
    _bounds_y: float = PrivateAttr(default=0.0)
    _bounds_w: float = PrivateAttr(default=0.0)
    _bounds_h: float = PrivateAttr(default=0.0)

    _program: moderngl.Program | None = PrivateAttr(default=None)
    _vao: moderngl.VertexArray | None = PrivateAttr(default=None)

    # Pre-computed per-frame ray heights: shape (total_frames, 128).
    # Only first ray_count slots per row are active.
    _bar_history: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros((0, 128), dtype="f4"))
    _bass_drive: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype="f4"))

    async def prepare(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        b = bounds or Rect(0, 0, ctx.job.width, ctx.job.height)
        self._canvas_h = float(ctx.job.height)
        self._bounds_x = float(b.x)
        self._bounds_y = float(b.y)
        self._bounds_w = float(b.width)
        self._bounds_h = float(b.height)
        self._bar_history = self._precompute_bar_history(ctx)
        frames = self.bus_timeline(ctx)
        self._bass_drive = precompute_bass_drive(frames, ctx.job.total_frames)

    def _precompute_bar_history(self, ctx: PrepareContext) -> np.ndarray:
        total = max(ctx.job.total_frames, 0)
        history = np.zeros((total, 128), dtype="f4")
        if total == 0:
            return history

        frames: list[AudioBusFrame] | None = self.bus_timeline(ctx)
        if not frames:
            return history

        n = self.ray_count
        bin_start = self.bin_start
        bin_idxs = np.empty(n, dtype=np.int64)
        for i in range(n):
            t = i / max(n - 1, 1)
            bin_idxs[i] = round(bin_start + t * (N_SPECTRUM - 1 - bin_start))

        s = float(self.smoothing)
        one_minus_s = 1.0 - s
        sens = float(self.sensitivity)
        n_bus = min(total, len(frames))
        amp_norm = _normalize_amplitudes(frames, n_bus)
        smoothed = np.zeros((total, n), dtype="f4")
        drive = np.zeros(total, dtype="f4")
        prev = np.zeros(n, dtype="f4")
        drive_state = 0.0
        for f in range(total):
            if f >= n_bus:
                prev = prev * s
                drive_state = drive_state * s
            else:
                freq = np.asarray(frames[f].spectrum, dtype="f4")
                raw = np.power(np.clip(freq[bin_idxs], 0.0, 1.0), _SPECTRUM_CURVE)
                prev = prev * s + raw * one_minus_s
                drive_state = drive_state * s + float(amp_norm[f]) * one_minus_s
            smoothed[f] = prev
            drive[f] = drive_state

        for f in range(total):
            history[f, :n] = _shape_ray_row(smoothed[f], float(drive[f]), sens)
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
        n = self.ray_count

        if self._bar_history.shape[0] > 0:
            f = max(0, min(ctx.time.frame, self._bar_history.shape[0] - 1))
            ray_heights = self._bar_history[f]
        else:
            bin_start = self.bin_start
            bin_idxs = np.empty(n, dtype=np.int64)
            for i in range(n):
                t = i / max(n - 1, 1)
                bin_idxs[i] = round(bin_start + t * (N_SPECTRUM - 1 - bin_start))
            af = ctx.audio_bus_frame
            freq = np.asarray(af.spectrum, dtype="f4")
            raw = np.power(np.clip(freq[bin_idxs], 0.0, 1.0), _SPECTRUM_CURVE)
            drive = float(np.clip(af.amplitude, 0.0, 1.0))
            shaped = _shape_ray_row(raw, drive, float(self.sensitivity))
            ray_heights = np.zeros(128, dtype="f4")
            ray_heights[:n] = shaped

        if self._bass_drive.shape[0] > 0:
            f = max(0, min(ctx.time.frame, self._bass_drive.shape[0] - 1))
            bass_drive = float(self._bass_drive[f])
        elif self.bus_active_for_draw(ctx):
            bass_drive = min(1.0, max(0.0, float(ctx.audio_bus_frame.bass)))
        else:
            bass_drive = 0.0
        scale_factor = 1.0 + float(self.scale_pulse) * bass_drive

        progress = _clip_progress(
            time_t=ctx.time.t,
            start=self.start,
            duration=self.duration,
            job_duration=ctx.job.duration,
        )
        pr, pg, pb, _ = resolve_color(self.progress_color, ctx.job.colors).rgba

        r, g, b, _ = resolve_color(self.color_primary, ctx.job.colors).rgba
        tr, tg, tb, _ = resolve_color(self.color_tip, ctx.job.colors).rgba

        self._set_uniform(prog, "u_res", (self._bounds_w, self._bounds_h))
        self._set_uniform(prog, "u_origin", (self._bounds_x, self._bounds_y))
        self._set_uniform(prog, "u_canvas_h", self._canvas_h)
        self._set_uniform(prog, "u_ray_count_f", float(n))
        self._set_uniform(prog, "u_ray_length", self.ray_length)
        self._set_uniform(prog, "u_angle", self.angle)
        self._set_uniform(prog, "u_offset_x", self.offset_x)
        self._set_uniform(prog, "u_offset_y", self.offset_y)
        self._set_uniform(prog, "u_width", self.width)
        self._set_uniform(prog, "u_color_primary", (r, g, b))
        self._set_uniform(prog, "u_color_tip", (tr, tg, tb))
        self._set_uniform(prog, "u_glow_intensity", self.glow_intensity)
        self._set_uniform(prog, "u_luma_alpha", self.luma_alpha)
        self._set_uniform(prog, "u_opacity", self.opacity)
        self._set_uniform(prog, "u_scale_factor", scale_factor)
        self._set_uniform(prog, "u_show_progress", 1.0 if self.show_progress else 0.0)
        self._set_uniform(prog, "u_progress", progress)
        self._set_uniform(prog, "u_progress_radius_frac", _PROGRESS_RING_RADIUS_FRAC)
        self._set_uniform(prog, "u_progress_track_gain", _PROGRESS_RING_TRACK_GAIN)
        self._set_uniform(prog, "u_progress_color", (pr, pg, pb))

        if "u_ray_heights[0]" in prog:
            for i in range(n):
                self._set_uniform(prog, f"u_ray_heights[{i}]", float(ray_heights[i]))
        elif "u_ray_heights" in prog:
            member = prog["u_ray_heights"]
            if isinstance(member, moderngl.Uniform):
                member.value = tuple(float(ray_heights[i]) for i in range(128))

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
