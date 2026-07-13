"""Directional dust overlay — soft drifting specks with onset gust acceleration."""

from __future__ import annotations

import math
from typing import Any, ClassVar, Literal

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
from pixfabrica_core.preview_dims import DEFAULT_REFERENCE_HEIGHT
from pixfabrica_core.random import SeededRandom
from pixfabrica_core.theme.color import Color, ColorToken, color_field, resolve_color

# ---------------------------------------------------------------------------
# Tunable defaults — passed to the shader as uniforms each frame.
# ---------------------------------------------------------------------------
_MAX_PARTICLES = 64
_PARTICLE_LOOP_CAP = 64
_MIN_SIZE_FRAC = 0.25
_SPECK_INTENSITY = 1.0
_SPECK_SHARPNESS = 3.2
_SPECK_ALPHA_SHARPNESS = 8.0
_PARTICLE_SPEED_MIN = 0.12
_PARTICLE_SPEED_RANGE = 0.08
_GUST_DECAY_K = 5.0

FALLBACK_INTERVAL_MIN_S = 2.0
FALLBACK_INTERVAL_MAX_S = 4.0
AMPLITUDE_GATE = 0.3
AMPLITUDE_SPIKE_DELTA = 0.15

_DIRECTION_INDEX = {"left": 0.0, "right": 1.0, "up": 2.0, "down": 3.0}

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
uniform float u_direction;
uniform float u_seed;
uniform float u_particle_count_f;
uniform float u_max_size;
uniform float u_spread;
uniform float u_brightness_variation;
uniform vec3  u_color;
uniform float u_speck_intensity;
uniform float u_speck_sharpness;
uniform float u_speck_alpha_sharpness;
uniform float u_particle_speed_min;
uniform float u_particle_speed_range;
uniform float u_min_size_frac;
uniform float u_luma_alpha;
uniform float u_opacity;

out vec4 frag_color;

float hash12(vec2 p) {
    p = fract(p * vec2(123.34, 456.21));
    p += dot(p, p + 45.32);
    return fract(p.x * p.y);
}

vec2 rot2(vec2 v, float a) {
    float c = cos(a), s = sin(a);
    return vec2(v.x * c - v.y * s, v.x * s + v.y * c);
}

void main() {
    float px = gl_FragCoord.x - u_origin.x;
    float py = (u_canvas_h - gl_FragCoord.y) - u_origin.y;

    vec2 uv = (vec2(px, py) - u_res * 0.5) / u_res.y;
    uv.y = -uv.y;

    float half_w = u_res.x / u_res.y * 0.5;
    float half_h = 0.5;
    float max_size_uv = u_max_size / u_res.y;
    float travel_dist = length(vec2(half_w * 2.0, half_h * 2.0)) * 1.05;

    vec3 col_acc = vec3(0.0);
    float alpha_acc = 0.0;
    int particle_count = int(u_particle_count_f);

    for (int i = 0; i < 64; i++) {
        if (i >= particle_count) break;
        float fi = float(i);

        float h0 = hash12(vec2(fi, u_seed));
        float h1 = hash12(vec2(fi, u_seed + 1.7));
        float h2 = hash12(vec2(fi, u_seed + 3.1));
        float h3 = hash12(vec2(fi, u_seed + 5.3));
        float h4 = hash12(vec2(fi, u_seed + 7.9));

        float phase = h0;
        float edge_pos = h1 * 2.0 - 1.0;
        float angle_off = (h2 * 2.0 - 1.0) * u_spread;
        float size_frac = mix(u_min_size_frac, 1.0, h3);
        float brightness = mix(1.0 - u_brightness_variation, 1.0, h4);

        float particle_speed = u_particle_speed_min + h1 * u_particle_speed_range;
        float progress = fract(u_eff_t * particle_speed + phase);

        vec2 entry;
        vec2 base_dir;
        if (u_direction < 0.5) {
            entry = vec2(half_w, edge_pos * half_h);
            base_dir = vec2(-1.0, 0.0);
        } else if (u_direction < 1.5) {
            entry = vec2(-half_w, edge_pos * half_h);
            base_dir = vec2(1.0, 0.0);
        } else if (u_direction < 2.5) {
            entry = vec2(edge_pos * half_w, -half_h);
            base_dir = vec2(0.0, 1.0);
        } else {
            entry = vec2(edge_pos * half_w, half_h);
            base_dir = vec2(0.0, -1.0);
        }

        vec2 travel_dir = rot2(base_dir, angle_off);
        vec2 p_uv = entry + travel_dir * progress * travel_dist;

        float speck_r = max_size_uv * size_frac;
        float dist = length(uv - p_uv);
        float r = dist / max(speck_r, 1e-5);
        float speck = exp(-r * r * u_speck_sharpness);
        float glow = u_speck_intensity * brightness * speck;
        float alpha_mask = exp(-r * r * u_speck_alpha_sharpness);
        float particle_a = clamp(alpha_mask * brightness, 0.0, 1.0);
        vec3 particle_rgb = u_color * glow;

        col_acc = particle_rgb + col_acc * (1.0 - particle_a);
        alpha_acc = particle_a + alpha_acc * (1.0 - particle_a);
    }

    vec3 rgb_out = pow(col_acc, vec3(1.0 / 2.2));
    float alpha_out = mix(u_opacity, alpha_acc * u_opacity, u_luma_alpha);
    frag_color = vec4(rgb_out * alpha_out, alpha_out);
}
"""

_QUAD = np.array(
    [-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0],
    dtype="f4",
)


def _passes_sensitivity(amplitude: float, sensitivity: float) -> bool:
    if sensitivity <= 0.0:
        return True
    return amplitude > sensitivity * AMPLITUDE_GATE


def _stamp_gust(
    gust_mult: np.ndarray,
    *,
    start_frame: int,
    gust_duration: float,
    gust_boost: float,
    fps: float,
) -> None:
    duration_frames = max(1, int(gust_duration * fps))
    denom = max(1, duration_frames - 1)
    for i in range(duration_frames):
        f = start_frame + i
        if f >= len(gust_mult):
            break
        age = float(i) / float(denom)
        mult = 1.0 + (gust_boost - 1.0) * math.exp(-_GUST_DECAY_K * age)
        gust_mult[f] = max(gust_mult[f], mult)


def precompute_dust_gust_envelope(
    *,
    total_frames: int,
    fps: float,
    clip_id: str,
    seed: int | None,
    sensitivity: float,
    gust_duration: float,
    gust_boost: float,
    bus_select: str | None,
    bus_frames: list[AudioBusFrame] | None,
) -> np.ndarray:
    """Per-frame speed multiplier (1.0 at rest, up to ``gust_boost`` during gusts)."""
    gust_mult = np.ones(total_frames, dtype=np.float32)
    if total_frames <= 0:
        return gust_mult

    rng = SeededRandom(seed) if seed is not None else SeededRandom.from_string(clip_id)
    bus_connected = bool((bus_select or "").strip())

    if bus_connected and bus_frames:
        n = min(total_frames, len(bus_frames))
        bus_has_onsets = any(bus_frames[f].onset for f in range(n))
        if bus_has_onsets:
            for f in range(n):
                af = bus_frames[f]
                if af.onset and _passes_sensitivity(af.amplitude, sensitivity):
                    _stamp_gust(
                        gust_mult,
                        start_frame=f,
                        gust_duration=gust_duration,
                        gust_boost=gust_boost,
                        fps=fps,
                    )
        else:
            for f in range(1, n):
                af = bus_frames[f]
                delta = af.amplitude - bus_frames[f - 1].amplitude
                if (
                    gust_mult[f] <= 1.0
                    and delta > AMPLITUDE_SPIKE_DELTA
                    and _passes_sensitivity(af.amplitude, sensitivity)
                ):
                    _stamp_gust(
                        gust_mult,
                        start_frame=f,
                        gust_duration=gust_duration,
                        gust_boost=gust_boost,
                        fps=fps,
                    )
    else:
        frame = int(rng.next() * fps * 0.5)
        while frame < total_frames:
            _stamp_gust(
                gust_mult,
                start_frame=frame,
                gust_duration=gust_duration,
                gust_boost=gust_boost,
                fps=fps,
            )
            gap_s = FALLBACK_INTERVAL_MIN_S + rng.next() * (
                FALLBACK_INTERVAL_MAX_S - FALLBACK_INTERVAL_MIN_S
            )
            frame += max(1, int(gap_s * fps))

    return gust_mult


def scale_max_size_for_job(
    max_size: float,
    job_height: float,
    *,
    reference_height: int = DEFAULT_REFERENCE_HEIGHT,
) -> float:
    """Scale a 1080p-reference pixel radius to the current output height."""
    ref = max(1, int(reference_height))
    height = max(1.0, float(job_height))
    return float(max_size) * (height / ref)


def precompute_dust_time_warp(
    gust_mult: np.ndarray,
    *,
    fps: float,
    speed: float,
) -> np.ndarray:
    """Integrate gust multipliers into monotonic animation time."""
    warp = np.zeros(gust_mult.shape[0], dtype=np.float32)
    if gust_mult.shape[0] == 0:
        return warp
    t = 0.0
    dt = float(speed) / max(fps, 1e-6)
    for f in range(gust_mult.shape[0]):
        warp[f] = t
        t += dt * float(gust_mult[f])
    return warp


class DriftingDustGL(AudioVisualMixin, ClipGL):
    """Directional dust specks — soft particles drift across the frame with onset gusts."""

    clip_type: ClassVar[str] = "std-drifting-dust-gl"
    clip_category: ClassVar[ClipCategory] = ClipCategory.PARTICLES
    clip_tags: ClassVar[list[str]] = [
        ClipTag.ANIMATED,
        ClipTag.GL,
        ClipTag.AUDIO_REACTIVE,
        ClipTag.PARTICLE,
    ]
    clip_presets: ClassVar[list[ClipPreset]] = [
        ClipPreset(id="default", label="Default", values={}),
        ClipPreset(
            id="heavy_gust",
            label="Heavy Gust",
            values={
                "particle_count": 48,
                "max_size": 18.0,
                "gust_boost": 4.0,
                "gust_duration": 0.6,
                "spread": 22.0,
            },
        ),
        ClipPreset(
            id="fine_mist",
            label="Fine Mist",
            values={
                "particle_count": 56,
                "max_size": 6.0,
                "gust_boost": 1.8,
                "gust_duration": 0.35,
                "brightness_variation": 0.8,
                "spread": 18.0,
                "speed": 0.75,
            },
        ),
    ]

    color: ColorToken | Color = color_field(ColorToken.NEUTRAL_VARIANT)
    direction: Literal["left", "right", "up", "down"] = Field(
        default="left",
        description="Drift direction; particles enter from the opposite edge",
    )
    particle_count: int = Field(
        default=32,
        ge=8,
        le=_MAX_PARTICLES,
        multiple_of=1,
        description="Number of dust particles",
    )
    max_size: float = Field(
        default=12.0,
        ge=1.0,
        le=48.0,
        multiple_of=0.5,
        description="Maximum speck radius in pixels at 1080p reference height",
    )
    spread: float = Field(
        default=15.0,
        ge=0.0,
        le=45.0,
        multiple_of=1.0,
        description="Angular spread in degrees around the drift direction",
    )
    brightness_variation: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        multiple_of=0.05,
        description="Per-particle brightness spread (0 = uniform)",
    )
    speed: float = Field(
        default=1.0,
        ge=0.25,
        le=3.0,
        multiple_of=0.05,
        description="Global animation speed multiplier",
    )
    gust_duration: float = Field(
        default=0.4,
        ge=0.1,
        le=1.0,
        multiple_of=0.05,
        description="Onset gust duration in seconds",
    )
    gust_boost: float = Field(
        default=2.5,
        ge=1.5,
        le=5.0,
        multiple_of=0.1,
        description="Peak speed multiplier during a gust",
    )
    sensitivity: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Minimum amplitude gate for onset triggers (0 = all onsets)",
    )
    seed: int | None = Field(
        default=None,
        description="Random seed for particle layout; None derives from clip id",
    )
    luma_alpha: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Luma-based transparency (1 = dark areas transparent)",
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
    _shader_seed: float = PrivateAttr(default=0.0)
    _time_warp: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype=np.float32))
    _program: moderngl.Program | None = PrivateAttr(default=None)
    _vao: moderngl.VertexArray | None = PrivateAttr(default=None)

    async def prepare(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        b = bounds or Rect(0, 0, ctx.job.width, ctx.job.height)
        self._canvas_h = float(ctx.job.height)
        self._bounds_x = float(b.x)
        self._bounds_y = float(b.y)
        self._bounds_w = float(b.width)
        self._bounds_h = float(b.height)

        rng = (
            SeededRandom(self.seed) if self.seed is not None else SeededRandom.from_string(self.id)
        )
        self._shader_seed = rng.next() * 1000.0

        total = max(ctx.job.total_frames, 0)
        gust_mult = precompute_dust_gust_envelope(
            total_frames=total,
            fps=float(ctx.job.fps),
            clip_id=self.id,
            seed=self.seed,
            sensitivity=float(self.sensitivity),
            gust_duration=float(self.gust_duration),
            gust_boost=float(self.gust_boost),
            bus_select=self.bus_select,
            bus_frames=self.bus_timeline(ctx),
        )
        self._time_warp = precompute_dust_time_warp(
            gust_mult,
            fps=float(ctx.job.fps),
            speed=float(self.speed),
        )

    def _set_uniform(self, prog: moderngl.Program, name: str, value: Any) -> None:
        if name not in prog:
            return
        member = prog[name]
        if isinstance(member, moderngl.Uniform):
            member.value = value

    def _set_shader_constants(self, prog: moderngl.Program) -> None:
        self._set_uniform(prog, "u_speck_intensity", _SPECK_INTENSITY)
        self._set_uniform(prog, "u_speck_sharpness", _SPECK_SHARPNESS)
        self._set_uniform(prog, "u_speck_alpha_sharpness", _SPECK_ALPHA_SHARPNESS)
        self._set_uniform(prog, "u_particle_speed_min", _PARTICLE_SPEED_MIN)
        self._set_uniform(prog, "u_particle_speed_range", _PARTICLE_SPEED_RANGE)
        self._set_uniform(prog, "u_min_size_frac", _MIN_SIZE_FRAC)

    def draw(self, ctx: RenderContext) -> None:
        gl: moderngl.Context = ctx.canvas

        if self._program is None:
            self._program = gl.program(vertex_shader=_VERT, fragment_shader=_FRAG)
            vbo = gl.buffer(_QUAD.tobytes())
            self._vao = gl.simple_vertex_array(self._program, vbo, "in_vert")
            self._set_shader_constants(self._program)

        prog = self._program
        f = max(0, min(ctx.time.frame, self._time_warp.shape[0] - 1)) if self._time_warp.size else 0
        eff_t = (
            float(self._time_warp[f])
            if self._time_warp.size
            else float(ctx.time.t) * float(self.speed)
        )

        r, g, b, _ = resolve_color(self.color, ctx.job.colors).rgba
        spread_rad = math.radians(float(self.spread))

        self._set_uniform(prog, "u_res", (self._bounds_w, self._bounds_h))
        self._set_uniform(prog, "u_origin", (self._bounds_x, self._bounds_y))
        self._set_uniform(prog, "u_canvas_h", self._canvas_h)
        self._set_uniform(prog, "u_eff_t", eff_t)
        self._set_uniform(prog, "u_direction", _DIRECTION_INDEX[self.direction])
        self._set_uniform(prog, "u_seed", self._shader_seed)
        self._set_uniform(prog, "u_particle_count_f", float(self.particle_count))
        effective_max_size = scale_max_size_for_job(float(self.max_size), float(ctx.job.height))
        self._set_uniform(prog, "u_max_size", effective_max_size)
        self._set_uniform(prog, "u_spread", spread_rad)
        self._set_uniform(prog, "u_brightness_variation", float(self.brightness_variation))
        self._set_uniform(prog, "u_color", (r, g, b))
        self._set_uniform(prog, "u_luma_alpha", float(self.luma_alpha))
        self._set_uniform(prog, "u_opacity", float(self.opacity))

        gl.scissor = (
            int(self._bounds_x),
            int(ctx.job.height - self._bounds_y - ctx.bounds.height),
            int(self._bounds_w),
            int(ctx.bounds.height),
        )

        assert self._vao is not None
        self._vao.render(moderngl.TRIANGLES)

        gl.scissor = None
