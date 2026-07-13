from __future__ import annotations

import math
from dataclasses import dataclass
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

# --- three.js DigitalGlitch / GlitchPass defaults ---
DISP_MAP_SIZE = 64
TRIGGER_MIN_FRAMES = 120
TRIGGER_MAX_FRAMES = 240
MILD_WINDOW_DIVISOR = 5
FULL_AMOUNT_DIVISOR = 30.0
MILD_AMOUNT_DIVISOR = 90.0
DEFAULT_AMOUNT = 0.08
DEFAULT_ANGLE = 0.02
DEFAULT_SEED = 0.02
DEFAULT_DISTORTION_X = 0.5
DEFAULT_DISTORTION_Y = 0.6
COL_S = 0.05
SNOW_SCALE = 200.0
SNOW_GAIN = 0.2
SEED_DISP_SCALE = 5.0

# Onset bus stamps (hybrid with procedural GlitchPass schedule)
ONSET_MILD_TAIL_FRAMES = 4
AMPLITUDE_GATE = 0.3
AMPLITUDE_SPIKE_DELTA = 0.15
ONSET_RNG_SUFFIX = ":bus-onset"

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
uniform sampler2D u_disp;
uniform vec2  u_resolution;
uniform int   u_byp;
uniform float u_amount;
uniform float u_angle;
uniform float u_seed;
uniform float u_seed_x;
uniform float u_seed_y;
uniform float u_distortion_x;
uniform float u_distortion_y;
uniform float u_col_s;
uniform float u_snow_scale;
uniform float u_snow_gain;
uniform float u_seed_disp_scale;
uniform float u_opacity;

in vec2 v_uv;
out vec4 fragColor;

float rand(vec2 co) {
    return fract(sin(dot(co.xy, vec2(12.9898, 78.233))) * 43758.5453);
}

vec3 digital_glitch(vec2 uv) {
    vec2 p = uv;
    float xs = floor(gl_FragCoord.x / 0.5);
    float ys = floor(gl_FragCoord.y / 0.5);

    float disp = texture(u_disp, p * u_seed * u_seed).r;

    if (p.y < u_distortion_x + u_col_s && p.y > u_distortion_x - u_col_s * u_seed) {
        if (u_seed_x > 0.0) {
            p.y = 1.0 - (p.y + u_distortion_y);
        } else {
            p.y = u_distortion_y;
        }
    }
    if (p.x < u_distortion_y + u_col_s && p.x > u_distortion_y - u_col_s * u_seed) {
        if (u_seed_y > 0.0) {
            p.x = u_distortion_x;
        } else {
            p.x = 1.0 - (p.x + u_distortion_x);
        }
    }

    p.x += disp * u_seed_x * (u_seed / u_seed_disp_scale);
    p.y += disp * u_seed_y * (u_seed / u_seed_disp_scale);

    vec2 offset = u_amount * vec2(cos(u_angle), sin(u_angle));
    vec2 p_r = clamp(p + offset, 0.0, 1.0);
    vec2 p_g = clamp(p, 0.0, 1.0);
    vec2 p_b = clamp(p - offset, 0.0, 1.0);

    vec3 rgb = vec3(
        texture(u_source, p_r).r,
        texture(u_source, p_g).g,
        texture(u_source, p_b).b
    );

    float snow = u_amount * u_snow_scale * rand(vec2(xs * u_seed, ys * u_seed * 50.0)) * u_snow_gain;
    return clamp(rgb + vec3(snow), 0.0, 1.0);
}

void main() {
    vec3 original = texture(u_source, v_uv).rgb;

    if (u_byp >= 1) {
        fragColor = vec4(original, 1.0);
        return;
    }

    vec3 glitched = digital_glitch(v_uv);
    fragColor = vec4(mix(original, glitched, u_opacity), 1.0);
}
"""

_QUAD = np.array([-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0], dtype="f4")


@dataclass(frozen=True)
class DigitalGlitchFrame:
    bypass: bool
    amount: float
    angle: float
    seed: float
    seed_x: float
    seed_y: float
    distortion_x: float
    distortion_y: float


def generate_displacement_map(size: int, rng: SeededRandom) -> np.ndarray:
    """Float32 red displacement map matching GlitchPass ``_generateHeightmap``."""
    count = size * size
    data = np.empty(count, dtype=np.float32)
    for i in range(count):
        data[i] = rng.next()
    return data.reshape(size, size)


def _passes_sensitivity(amplitude: float, sensitivity: float) -> bool:
    if sensitivity <= 0.0:
        return True
    return amplitude > sensitivity * AMPLITUDE_GATE


def _sample_full_glitch(rng: SeededRandom, strength: float) -> DigitalGlitchFrame:
    return DigitalGlitchFrame(
        bypass=False,
        amount=(rng.next() / FULL_AMOUNT_DIVISOR) * strength,
        angle=rng.next() * (2.0 * math.pi) - math.pi,
        seed=rng.next(),
        seed_x=rng.next() * 2.0 - 1.0,
        seed_y=rng.next() * 2.0 - 1.0,
        distortion_x=rng.next(),
        distortion_y=rng.next(),
    )


def _sample_mild_glitch(rng: SeededRandom, strength: float) -> DigitalGlitchFrame:
    return DigitalGlitchFrame(
        bypass=False,
        amount=(rng.next() / MILD_AMOUNT_DIVISOR) * strength,
        angle=rng.next() * (2.0 * math.pi) - math.pi,
        seed=rng.next(),
        seed_x=rng.next() * 0.6 - 0.3,
        seed_y=rng.next() * 0.6 - 0.3,
        distortion_x=rng.next(),
        distortion_y=rng.next(),
    )


def _stamp_onset_burst(
    frames: list[DigitalGlitchFrame],
    start_frame: int,
    rng: SeededRandom,
    strength: float,
) -> None:
    if start_frame >= len(frames):
        return
    frames[start_frame] = _sample_full_glitch(rng, strength)
    for i in range(1, ONSET_MILD_TAIL_FRAMES):
        f = start_frame + i
        if f >= len(frames):
            break
        frames[f] = _sample_mild_glitch(rng, strength)


def apply_bus_onset_stamps(
    frames: list[DigitalGlitchFrame],
    *,
    clip_id: str,
    seed: int | None,
    strength: float,
    sensitivity: float,
    bus_select: str | None,
    bus_frames: list[AudioBusFrame] | None,
) -> list[DigitalGlitchFrame]:
    """Overlay onset-triggered full + mild glitches on the procedural schedule."""
    bus_connected = bool((bus_select or "").strip())
    if not bus_connected or not bus_frames or not frames:
        return frames

    rng_key = f"{clip_id}{ONSET_RNG_SUFFIX}" if seed is None else f"{seed}{ONSET_RNG_SUFFIX}"
    rng = SeededRandom.from_string(rng_key)
    n = min(len(frames), len(bus_frames))

    bus_has_onsets = any(bus_frames[f].onset for f in range(n))
    if bus_has_onsets:
        for f in range(n):
            af = bus_frames[f]
            if af.onset and _passes_sensitivity(af.amplitude, sensitivity):
                _stamp_onset_burst(frames, f, rng, strength)
    else:
        for f in range(1, n):
            af = bus_frames[f]
            delta = af.amplitude - bus_frames[f - 1].amplitude
            if delta > AMPLITUDE_SPIKE_DELTA and _passes_sensitivity(af.amplitude, sensitivity):
                _stamp_onset_burst(frames, f, rng, strength)

    return frames


def precompute_glitch_pass_frames(
    *,
    total_frames: int,
    clip_id: str,
    seed: int | None,
    go_wild: bool,
    strength: float,
    sensitivity: float = 1.0,
    bus_select: str | None = None,
    bus_frames: list[AudioBusFrame] | None = None,
) -> list[DigitalGlitchFrame]:
    """Deterministic port of three.js ``GlitchPass.render`` frame scheduling."""
    if total_frames <= 0:
        return []

    rng = SeededRandom(seed) if seed is not None else SeededRandom.from_string(clip_id)
    strength = max(0.0, float(strength))
    cur_f = 0
    rand_x = rng.next_int(TRIGGER_MIN_FRAMES, TRIGGER_MAX_FRAMES)
    mild_limit = max(1, rand_x // MILD_WINDOW_DIVISOR)
    frames: list[DigitalGlitchFrame] = []

    for _ in range(total_frames):
        bypass = False
        amount = DEFAULT_AMOUNT * strength
        angle = DEFAULT_ANGLE
        seed_val = DEFAULT_SEED
        seed_x = DEFAULT_SEED
        seed_y = DEFAULT_SEED
        distortion_x = DEFAULT_DISTORTION_X
        distortion_y = DEFAULT_DISTORTION_Y

        if cur_f % rand_x == 0 or go_wild:
            bypass = False
            sampled = _sample_full_glitch(rng, strength)
            amount = sampled.amount
            angle = sampled.angle
            seed_val = sampled.seed
            seed_x = sampled.seed_x
            seed_y = sampled.seed_y
            distortion_x = sampled.distortion_x
            distortion_y = sampled.distortion_y
            cur_f = 0
            rand_x = rng.next_int(TRIGGER_MIN_FRAMES, TRIGGER_MAX_FRAMES)
            mild_limit = max(1, rand_x // MILD_WINDOW_DIVISOR)
        elif cur_f % rand_x < mild_limit:
            bypass = False
            sampled = _sample_mild_glitch(rng, strength)
            amount = sampled.amount
            angle = sampled.angle
            seed_val = sampled.seed
            seed_x = sampled.seed_x
            seed_y = sampled.seed_y
            distortion_x = sampled.distortion_x
            distortion_y = sampled.distortion_y
        elif not go_wild:
            bypass = True

        cur_f += 1
        frames.append(
            DigitalGlitchFrame(
                bypass=bypass,
                amount=amount,
                angle=angle,
                seed=seed_val,
                seed_x=seed_x,
                seed_y=seed_y,
                distortion_x=distortion_x,
                distortion_y=distortion_y,
            )
        )

    return apply_bus_onset_stamps(
        frames,
        clip_id=clip_id,
        seed=seed,
        strength=strength,
        sensitivity=sensitivity,
        bus_select=bus_select,
        bus_frames=bus_frames,
    )


class DigitalGlitch(AudioVisualMixin, GLPostProcessClip):
    """Digital block tear and RGB-shift glitch (three.js DigitalGlitch).

    Most frames pass through clean; periodic bursts apply displacement-map
    tearing, axis inversions, chromatic offset, and snow noise. Schedule matches
    ``GlitchPass`` with seeded randomness for reproducible export. When
    ``bus_select`` is set, audio onsets stamp extra full + mild glitch bursts
    on top of the procedural schedule. Stack on a GLEffectTrack
    (``std-post-track``).
    """

    clip_type: ClassVar[str] = "std-digital-glitch"
    clip_category: ClassVar[ClipCategory] = ClipCategory.POSTPROCESS
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED, ClipTag.GL]

    strength: float = Field(
        default=1.0,
        ge=0.0,
        le=2.0,
        multiple_of=0.1,
        description="Glitch amount scale (RGB offset and noise)",
    )
    opacity: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Blend between original (0) and glitched (1) on active frames",
    )
    go_wild: bool = Field(
        default=False,
        description="When true, glitch every frame (three.js GlitchPass goWild)",
    )
    seed: int | None = Field(
        default=None,
        description="Random seed for displacement map and burst schedule; None derives from clip id",
    )

    _program: moderngl.Program | None = PrivateAttr(default=None)
    _vao: moderngl.VertexArray | None = PrivateAttr(default=None)
    _disp_texture: moderngl.Texture | None = PrivateAttr(default=None)
    _disp_data: np.ndarray | None = PrivateAttr(default=None)
    _frames: list[DigitalGlitchFrame] = PrivateAttr(default_factory=list)
    _res: tuple[float, float] = PrivateAttr(default=(0.0, 0.0))

    async def prepare(self, ctx: PrepareContext, _bounds: Rect | None = None) -> None:
        self._res = (float(ctx.job.width), float(ctx.job.height))
        rng = (
            SeededRandom(self.seed) if self.seed is not None else SeededRandom.from_string(self.id)
        )
        self._disp_data = generate_displacement_map(DISP_MAP_SIZE, rng)
        self._frames = precompute_glitch_pass_frames(
            total_frames=max(ctx.job.total_frames, 0),
            clip_id=self.id,
            seed=self.seed,
            go_wild=bool(self.go_wild),
            strength=float(self.strength),
            sensitivity=float(self.sensitivity),
            bus_select=self.bus_select,
            bus_frames=self.bus_timeline(ctx),
        )
        self._disp_texture = None

    def _set_uniform(self, prog: moderngl.Program, name: str, value: Any) -> None:
        if name in prog:
            member = prog[name]
            if isinstance(member, moderngl.Uniform):
                member.value = value

    def _ensure_disp_texture(self, gl: moderngl.Context) -> None:
        if self._disp_texture is not None or self._disp_data is None:
            return
        tex = gl.texture((DISP_MAP_SIZE, DISP_MAP_SIZE), 1, dtype="f4")
        tex.write(self._disp_data.tobytes())
        tex.filter = (moderngl.NEAREST, moderngl.NEAREST)
        tex.repeat_x = True
        tex.repeat_y = True
        self._disp_texture = tex

    def draw(self, ctx: RenderContext) -> None:
        if ctx.source_texture is None:
            return

        gl: moderngl.Context = ctx.canvas
        self._ensure_disp_texture(gl)

        if self._program is None:
            self._program = gl.program(vertex_shader=_VERT, fragment_shader=_FRAG)
            vbo = gl.buffer(_QUAD.tobytes())
            self._vao = gl.simple_vertex_array(self._program, vbo, "in_vert")

        f = max(0, min(ctx.time.frame, len(self._frames) - 1)) if self._frames else 0
        state = (
            self._frames[f]
            if self._frames
            else DigitalGlitchFrame(
                bypass=True,
                amount=0.0,
                angle=0.0,
                seed=0.0,
                seed_x=0.0,
                seed_y=0.0,
                distortion_x=0.0,
                distortion_y=0.0,
            )
        )

        prog = self._program
        ctx.source_texture.use(location=0)
        assert self._disp_texture is not None
        self._disp_texture.use(location=1)

        self._set_uniform(prog, "u_source", 0)
        self._set_uniform(prog, "u_disp", 1)
        self._set_uniform(prog, "u_resolution", self._res)
        self._set_uniform(prog, "u_byp", 1 if state.bypass else 0)
        self._set_uniform(prog, "u_amount", float(state.amount))
        self._set_uniform(prog, "u_angle", float(state.angle))
        self._set_uniform(prog, "u_seed", float(state.seed))
        self._set_uniform(prog, "u_seed_x", float(state.seed_x))
        self._set_uniform(prog, "u_seed_y", float(state.seed_y))
        self._set_uniform(prog, "u_distortion_x", float(state.distortion_x))
        self._set_uniform(prog, "u_distortion_y", float(state.distortion_y))
        self._set_uniform(prog, "u_col_s", COL_S)
        self._set_uniform(prog, "u_snow_scale", SNOW_SCALE)
        self._set_uniform(prog, "u_snow_gain", SNOW_GAIN)
        self._set_uniform(prog, "u_seed_disp_scale", SEED_DISP_SCALE)
        self._set_uniform(prog, "u_opacity", float(self.opacity))

        assert self._vao is not None
        self._vao.render(moderngl.TRIANGLES)
