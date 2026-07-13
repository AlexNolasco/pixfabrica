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

// Star Nest by Pablo Roman Andrioli — MIT License
// Adapted for Pixfabrica: theme tinting, audio reactivity, band crop.

uniform vec2  u_res;
uniform vec2  u_origin;
uniform float u_canvas_h;
uniform float u_t;
uniform vec3  u_color;
uniform float u_zoom;
uniform float u_speed;
uniform float u_brightness;
uniform float u_darkmatter;
uniform float u_star_density;
uniform float u_band_height;
uniform float u_offset_y;
uniform float u_intensity;
uniform float u_luma_alpha;
uniform float u_opacity;
uniform float u_beat_flash;
uniform float u_bass;
uniform float u_high;
uniform float u_amplitude;

out vec4 frag_color;

// Baked quality settings — tuned for GPU render throughput.
#define ITERATIONS  15
#define VOLSTEPS    15
#define STEPSIZE    0.1
#define TILE        0.850
#define DISTFADING  0.730

void main() {
    float px = gl_FragCoord.x - u_origin.x;
    float py = (u_canvas_h - gl_FragCoord.y) - u_origin.y;

    if (px < 0.0 || px >= u_res.x || py < 0.0 || py >= u_res.y) discard;

    // Vertical band crop: band_height=1 fills full bounds, <1 clips to a strip.
    float band_half = u_band_height * u_res.y * 0.5;
    float center_y  = u_offset_y * u_res.y;
    if (abs(py - center_y) > band_half) discard;

    vec2 uv = vec2(px, py) / u_res - 0.5;
    uv.y *= u_res.y / u_res.x;

    float eff_zoom = u_zoom + u_bass * 0.15;
    vec3 dir  = vec3(uv * eff_zoom, 1.0);
    float time = u_t * u_speed * 0.010 + 0.25;

    float a1  = 0.5;
    float a2  = 0.8;
    mat2 rot1 = mat2( cos(a1), sin(a1), -sin(a1), cos(a1));
    mat2 rot2 = mat2( cos(a2), sin(a2), -sin(a2), cos(a2));
    dir.xz *= rot1;
    dir.xy *= rot2;

    vec3 from = vec3(1.0, 0.5, 0.5);
    from += vec3(time * 2.0, time, -2.0);
    from.xz *= rot1;
    from.xy *= rot2;

    float eff_darkmatter = max(0.0, u_darkmatter - u_amplitude * 0.2);
    float sat = 0.850 + u_high * 0.15;
    float eff_brightness = 0.0015 * u_brightness * (1.0 + u_bass * 2.0 + u_beat_flash * 1.5);

    float s = 0.1, fade = 1.0;
    vec3 v = vec3(0.0);

    for (int r = 0; r < VOLSTEPS; r++) {
        vec3 p = from + s * dir * 0.5;
        p = abs(vec3(TILE) - mod(p, vec3(TILE * 2.0)));
        float pa = 0.0, a = 0.0;
        for (int i = 0; i < ITERATIONS; i++) {
            p  = abs(p) / max(dot(p, p), 1e-6) - u_star_density;
            a += abs(length(p) - pa);
            pa = length(p);
        }
        float dm = max(0.0, eff_darkmatter - a * a * 0.001);
        a *= a * a;
        if (r > 6) fade *= 1.0 - dm;
        v += fade;
        v += vec3(s, s*s, s*s*s*s) * a * eff_brightness * fade;
        fade *= DISTFADING;
        s    += STEPSIZE;
        if (fade < 0.001) break;
    }

    v = mix(vec3(length(v)), v, sat);
    vec3 col = v * 0.01 * u_color * u_intensity;

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


class StarNestGL(ClipGL, AudioVisualMixin):
    """Volumetric star field fly-through (Star Nest by Pablo Roman Andrioli, MIT).
    Audio-reactive: beat flashes stars, bass boosts brightness and zoom,
    treble enriches color, amplitude clears dark matter."""

    clip_type: ClassVar[str] = "std-star-nest-gl"
    clip_category: ClassVar[ClipCategory] = ClipCategory.BACKGROUND
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED, ClipTag.GL, ClipTag.AUDIO_REACTIVE]
    clip_presets: ClassVar[list[ClipPreset]] = [
        ClipPreset(
            id="let_there_be_light",
            label="Let There Be Light",
            values={
                "zoom": 0.4,
                "speed": 5.0,
                "brightness": 5.0,
                "luma_alpha": 0.2,
            },
        ),
        ClipPreset(
            id="dark_matter",
            label="Dark Matter",
            values={
                "zoom": 0.4,
                "speed": 0.4,
                "brightness": 1.4,
                "darkmatter": 0.5,
                "star_density": 0.45,
                "intensity": 0.1,
                "luma_alpha": 0.0,
            },
        ),
        ClipPreset(
            id="hubble",
            label="Hubble",
            values={
                "zoom": 1.5,
                "speed": 0.2,
                "brightness": 0.1,
                "darkmatter": 0.0,
                "star_density": 0.65,
                "luma_alpha": 0.0,
            },
        ),
    ]

    color_primary: ColorToken | Color = color_field(ColorToken.PRIMARY)

    offset_y: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Vertical band position within bounds (0 = top, 0.5 = center, 1 = bottom)",
    )
    band_height: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Vertical extent as fraction of clip bounds (1 = full, 0.5 = half-height band)",
    )
    opacity: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Overall layer opacity",
    )
    zoom: float = Field(
        default=0.8,
        ge=0.4,
        le=1.5,
        multiple_of=0.05,
        description="Field of view — wider shows more stars",
    )
    speed: float = Field(
        default=1.0,
        ge=0.0,
        le=5.0,
        multiple_of=0.1,
        description="Fly-through speed multiplier (1 = original)",
    )
    brightness: float = Field(
        default=1.0,
        ge=0.1,
        le=5.0,
        multiple_of=0.1,
        description="Star brightness multiplier (1 = original)",
    )
    darkmatter: float = Field(
        default=0.3,
        ge=0.0,
        le=0.5,
        multiple_of=0.01,
        description="Dark matter density — higher obscures more stars",
    )
    star_density: float = Field(
        default=0.53,
        ge=0.45,
        le=0.65,
        multiple_of=0.01,
        description="Star clustering density (lower = sparser, higher = denser)",
    )
    intensity: float = Field(
        default=1.0,
        ge=0.0,
        le=3.0,
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
            beat_flash = (
                float(self._beat_decay_frames[f]) if self._beat_decay_frames.shape[0] > 0 else 0.0
            )
        else:
            af = ctx.audio_bus_frame
            bass = self.scale_audio(float(af.bass))
            high = self.scale_audio(float(af.high))
            amp = self.scale_audio(float(af.amplitude))
            beat_flash = 1.5 if af.beat else 0.0
        return bass, high, amp, beat_flash

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

        r, g, b, _ = resolve_color(self.color_primary, ctx.job.colors).rgba
        self._set_uniform(prog, "u_color", (r, g, b))

        self._set_uniform(prog, "u_zoom", self.zoom)
        self._set_uniform(prog, "u_speed", self.speed)
        self._set_uniform(prog, "u_brightness", self.brightness)
        self._set_uniform(prog, "u_darkmatter", self.darkmatter)
        self._set_uniform(prog, "u_star_density", self.star_density)
        self._set_uniform(prog, "u_band_height", self.band_height)
        self._set_uniform(prog, "u_offset_y", self.offset_y)
        self._set_uniform(prog, "u_intensity", self.intensity)
        self._set_uniform(prog, "u_luma_alpha", self.luma_alpha)
        self._set_uniform(prog, "u_opacity", self.opacity)

        bass, high, amp, beat_flash = self._audio_drives_for_frame(ctx)
        self._set_uniform(prog, "u_beat_flash", beat_flash)
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
