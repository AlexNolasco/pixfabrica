from __future__ import annotations

from typing import Any, ClassVar

import moderngl
import numpy as np
from pydantic import Field, PrivateAttr

from pixfabrica_core.audio.bus import AudioBusFrame
from pixfabrica_core.audio.mixin import AudioVisualMixin
from pixfabrica_core.clips import (
    ClipCategory,
    ClipTag,
    GLPostProcessClip,
    PrepareContext,
    RenderContext,
)
from pixfabrica_core.graphics import Rect
from pixfabrica_core.random import SeededRandom

_VERT = """
#version 330 core
in vec2 in_vert;
out vec2 v_uv;
void main() {
    v_uv = in_vert * 0.5 + 0.5;
    gl_Position = vec4(in_vert, 0.0, 1.0);
}
"""

_FRAG = """
#version 330 core

uniform sampler2D u_source;
uniform vec2  u_resolution;
uniform float u_band_h;
uniform float u_intensity;
uniform float u_rgb_offset;
uniform float u_slice_shift;
uniform float u_rgb_sign;
uniform float u_burst_seed;
uniform float u_opacity;

in vec2 v_uv;
out vec4 fragColor;

float hash1d(float x) {
    return fract(sin(x * 127.1) * 43758.5453);
}

void main() {
    vec3 original = texture(u_source, v_uv).rgb;

    if (u_intensity <= 0.0) {
        fragColor = vec4(original, 1.0);
        return;
    }

    float band = floor(v_uv.y * u_resolution.y / max(u_band_h, 1.0));
    float row_shift = (hash1d(band + u_burst_seed) - 0.5) * 2.0 * u_slice_shift;
    vec2 uv = v_uv + vec2(row_shift, 0.0);
    uv = clamp(uv, 0.0, 1.0);

    vec2 offset = vec2(u_rgb_offset * u_rgb_sign, 0.0);
    vec2 uv_r = clamp(uv + offset, 0.0, 1.0);
    vec2 uv_b = clamp(uv - offset, 0.0, 1.0);

    vec3 glitched = vec3(
        texture(u_source, uv_r).r,
        texture(u_source, uv).g,
        texture(u_source, uv_b).b
    );

    vec3 processed = mix(original, glitched, u_intensity);
    fragColor = vec4(mix(original, processed, u_opacity), 1.0);
}
"""

_QUAD = np.array([-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0], dtype="f4")

DECAY_ENVELOPE: tuple[float, ...] = (1.0, 0.6, 0.25, 0.05)
FALLBACK_INTERVAL_MIN_S = 2.0
FALLBACK_INTERVAL_MAX_S = 4.0
REF_HEIGHT = 1080.0
BAND_HEIGHT_PX = 12.0
AMPLITUDE_GATE = 0.3
AMPLITUDE_SPIKE_DELTA = 0.15
MAX_RGB_OFFSET_UV = 0.035
MAX_SLICE_SHIFT_UV = 0.06


def band_height_px(job_height: float) -> float:
    return BAND_HEIGHT_PX * (job_height / REF_HEIGHT)


def _passes_sensitivity(amplitude: float, sensitivity: float) -> bool:
    if sensitivity <= 0.0:
        return True
    return amplitude > sensitivity * AMPLITUDE_GATE


def _stamp_burst(
    intensity: np.ndarray,
    burst_seed: np.ndarray,
    rgb_sign: np.ndarray,
    start_frame: int,
    seed: float,
    sign: float,
) -> None:
    for i, decay in enumerate(DECAY_ENVELOPE):
        f = start_frame + i
        if f >= len(intensity):
            break
        if decay >= intensity[f]:
            intensity[f] = decay
            burst_seed[f] = seed
            rgb_sign[f] = sign


def precompute_glitch_envelope(
    *,
    total_frames: int,
    fps: float,
    clip_id: str,
    seed: int | None,
    sensitivity: float,
    bus_select: str | None,
    bus_frames: list[AudioBusFrame] | None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per-frame burst intensity, row-hash seed, and RGB split sign."""
    intensity = np.zeros(total_frames, dtype=np.float32)
    burst_seed = np.zeros(total_frames, dtype=np.float32)
    rgb_sign = np.ones(total_frames, dtype=np.float32)

    if total_frames <= 0:
        return intensity, burst_seed, rgb_sign

    rng = SeededRandom(seed) if seed is not None else SeededRandom.from_string(clip_id)
    bus_connected = bool((bus_select or "").strip())

    if bus_connected:
        if bus_frames:
            n = min(total_frames, len(bus_frames))
            bus_has_onsets = any(bus_frames[f].onset for f in range(n))
            if bus_has_onsets:
                for f in range(n):
                    af = bus_frames[f]
                    if af.onset and _passes_sensitivity(af.amplitude, sensitivity):
                        _stamp_burst(
                            intensity,
                            burst_seed,
                            rgb_sign,
                            f,
                            rng.next() * 10000.0,
                            1.0 if rng.next() >= 0.5 else -1.0,
                        )
            else:
                for f in range(1, n):
                    af = bus_frames[f]
                    delta = af.amplitude - bus_frames[f - 1].amplitude
                    if (
                        intensity[f] == 0.0
                        and delta > AMPLITUDE_SPIKE_DELTA
                        and _passes_sensitivity(af.amplitude, sensitivity)
                    ):
                        _stamp_burst(
                            intensity,
                            burst_seed,
                            rgb_sign,
                            f,
                            rng.next() * 10000.0,
                            1.0 if rng.next() >= 0.5 else -1.0,
                        )
    else:
        frame = int(rng.next() * fps * 0.5)
        while frame < total_frames:
            _stamp_burst(
                intensity,
                burst_seed,
                rgb_sign,
                frame,
                rng.next() * 10000.0,
                1.0 if rng.next() >= 0.5 else -1.0,
            )
            gap_s = FALLBACK_INTERVAL_MIN_S + rng.next() * (
                FALLBACK_INTERVAL_MAX_S - FALLBACK_INTERVAL_MIN_S
            )
            frame += max(1, int(gap_s * fps))

    return intensity, burst_seed, rgb_sign


class Glitch(AudioVisualMixin, GLPostProcessClip):
    """Onset-triggered RGB tear and row slice shift post-processing effect.

    Fires on audio onsets when ``bus_select`` is set. Timelines with no onset
    flags (e.g. simple analyzer) fall back to amplitude-rise spikes. Without a
    bus, schedules low-rate procedural bursts via ``SeededRandom``. Stack after
    VHS/scanlines, before Rain Drops, on a GLEffectTrack (``std-post-track``).
    """

    clip_type: ClassVar[str] = "std-glitch"
    clip_category: ClassVar[ClipCategory] = ClipCategory.POSTPROCESS
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED, ClipTag.GL]

    strength: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="RGB channel offset and row slice shift magnitude",
    )
    opacity: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Blend between original (0) and glitched (1)",
    )
    sensitivity: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Minimum amplitude gate for onset triggers (0 = all onsets)",
    )
    seed: int | None = Field(
        default=None,
        description="Random seed for burst schedule and variation; None derives from clip id",
    )

    _program: moderngl.Program | None = PrivateAttr(default=None)
    _vao: moderngl.VertexArray | None = PrivateAttr(default=None)
    _res: tuple[float, float] = PrivateAttr(default=(0.0, 0.0))
    _band_h: float = PrivateAttr(default=0.0)
    _intensity: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype=np.float32))
    _burst_seed: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype=np.float32))
    _rgb_sign: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype=np.float32))

    async def prepare(self, ctx: PrepareContext, _bounds: Rect | None = None) -> None:
        self._res = (float(ctx.job.width), float(ctx.job.height))
        self._band_h = band_height_px(float(ctx.job.height))
        self._intensity, self._burst_seed, self._rgb_sign = precompute_glitch_envelope(
            total_frames=max(ctx.job.total_frames, 0),
            fps=float(ctx.job.fps),
            clip_id=self.id,
            seed=self.seed,
            sensitivity=float(self.sensitivity),
            bus_select=self.bus_select,
            bus_frames=self.bus_timeline(ctx),
        )

    def _set_uniform(self, prog: moderngl.Program, name: str, value: Any) -> None:
        if name in prog:
            member = prog[name]
            if isinstance(member, moderngl.Uniform):
                member.value = value

    def draw(self, ctx: RenderContext) -> None:
        if ctx.source_texture is None:
            return

        gl: moderngl.Context = ctx.canvas

        if self._program is None:
            self._program = gl.program(vertex_shader=_VERT, fragment_shader=_FRAG)
            vbo = gl.buffer(_QUAD.tobytes())
            self._vao = gl.simple_vertex_array(self._program, vbo, "in_vert")

        f = max(0, min(ctx.time.frame, self._intensity.shape[0] - 1)) if self._intensity.size else 0
        intensity = float(self._intensity[f]) if self._intensity.size else 0.0
        burst_seed = float(self._burst_seed[f]) if self._burst_seed.size else 0.0
        rgb_sign = float(self._rgb_sign[f]) if self._rgb_sign.size else 1.0

        strength = float(self.strength)
        rgb_offset = intensity * strength * MAX_RGB_OFFSET_UV
        slice_shift = intensity * strength * MAX_SLICE_SHIFT_UV

        prog = self._program
        ctx.source_texture.use(location=0)
        self._set_uniform(prog, "u_source", 0)
        self._set_uniform(prog, "u_resolution", self._res)
        self._set_uniform(prog, "u_band_h", self._band_h)
        self._set_uniform(prog, "u_intensity", intensity)
        self._set_uniform(prog, "u_rgb_offset", rgb_offset)
        self._set_uniform(prog, "u_slice_shift", slice_shift)
        self._set_uniform(prog, "u_rgb_sign", rgb_sign)
        self._set_uniform(prog, "u_burst_seed", burst_seed)
        self._set_uniform(prog, "u_opacity", self.opacity)

        assert self._vao is not None
        self._vao.render(moderngl.TRIANGLES)
