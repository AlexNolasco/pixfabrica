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
uniform float u_aspect;
uniform float u_strength;
uniform float u_speed;
uniform float u_width;
uniform float u_opacity;
uniform float u_ring_age_0;
uniform float u_ring_age_1;
uniform float u_ring_age_2;

in vec2 v_uv;
out vec4 fragColor;

const float MAX_RADIUS = 1.5;
const float PI = 3.14159265358979;

vec2 ring_displace(vec2 uv, float age) {
    if (age < 0.0) return vec2(0.0);

    float radius = age * u_speed;
    if (radius >= MAX_RADIUS) return vec2(0.0);

    // amplitude fades linearly as ring expands
    float amplitude = u_strength * (1.0 - radius / MAX_RADIUS);

    // aspect-correct distance from center so ring is circular on screen
    vec2 diff = uv - vec2(0.5);
    diff.x *= u_aspect;
    float dist = length(diff);

    // sine ripple: one full cycle within ±width/2 of ring edge
    float t = (dist - radius) / max(u_width, 0.001);
    if (abs(t) >= 0.5) return vec2(0.0);

    float wave = sin(t * 2.0 * PI);

    // outward direction in screen space, converted back to UV space
    vec2 dir_screen = (dist > 0.001) ? normalize(diff) : vec2(0.0, 1.0);
    vec2 dir_uv = dir_screen * vec2(1.0 / u_aspect, 1.0);

    return dir_uv * (wave * amplitude);
}

void main() {
    vec3 original = texture(u_source, v_uv).rgb;

    vec2 uv = v_uv
        + ring_displace(v_uv, u_ring_age_0)
        + ring_displace(v_uv, u_ring_age_1)
        + ring_displace(v_uv, u_ring_age_2);
    uv = clamp(uv, 0.0, 1.0);

    vec3 warped = texture(u_source, uv).rgb;
    fragColor = vec4(mix(original, warped, u_opacity), 1.0);
}
"""

_QUAD = np.array([-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0], dtype="f4")

MAX_RINGS = 3
MAX_RADIUS = 1.5
AMPLITUDE_GATE = 0.3
AMPLITUDE_SPIKE_DELTA = 0.15
FALLBACK_INTERVAL_MIN_S = 2.0
FALLBACK_INTERVAL_MAX_S = 4.0


def _passes_sensitivity(amplitude: float, sensitivity: float) -> bool:
    if sensitivity <= 0.0:
        return True
    return amplitude > sensitivity * AMPLITUDE_GATE


def _precompute_spawn_frames(
    *,
    total_frames: int,
    fps: float,
    clip_id: str,
    seed: int | None,
    sensitivity: float,
    bus_select: str | None,
    bus_frames: list[AudioBusFrame] | None,
) -> list[int]:
    if total_frames <= 0:
        return []

    spawns: list[int] = []
    rng = SeededRandom(seed) if seed is not None else SeededRandom.from_string(clip_id)
    bus_connected = bool((bus_select or "").strip())

    if bus_connected and bus_frames:
        n = min(total_frames, len(bus_frames))
        bus_has_onsets = any(bus_frames[f].onset for f in range(n))
        if bus_has_onsets:
            for f in range(n):
                af = bus_frames[f]
                if af.onset and _passes_sensitivity(af.amplitude, sensitivity):
                    spawns.append(f)
        else:
            # amplitude-rise fallback when onset flags are absent
            for f in range(1, n):
                af = bus_frames[f]
                delta = af.amplitude - bus_frames[f - 1].amplitude
                if delta > AMPLITUDE_SPIKE_DELTA and _passes_sensitivity(af.amplitude, sensitivity):
                    spawns.append(f)
    else:
        frame = int(rng.next() * fps * 0.5)
        while frame < total_frames:
            spawns.append(frame)
            gap_s = FALLBACK_INTERVAL_MIN_S + rng.next() * (
                FALLBACK_INTERVAL_MAX_S - FALLBACK_INTERVAL_MIN_S
            )
            frame += max(1, int(gap_s * fps))

    return spawns


class Shockwave(AudioVisualMixin, GLPostProcessClip):
    """Onset-triggered radial UV ripple that expands outward from center as a
    circular shockwave.

    Each audio onset spawns a new ring; up to three rings travel simultaneously.
    Rings expand at ``speed`` screen-height-units/sec and fade as they grow,
    retiring when they clear the frame diagonal. Without a bus, schedules
    low-rate procedural bursts via ``SeededRandom``. Stack after VHS/scanlines
    on a GLEffectTrack (``std-post-track``).
    """

    clip_type: ClassVar[str] = "std-shockwave"
    clip_category: ClassVar[ClipCategory] = ClipCategory.POSTPROCESS
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED, ClipTag.GL]

    width: float = Field(
        default=0.15,
        ge=0.02,
        le=0.5,
        multiple_of=0.01,
        description="Sine ripple band width in screen-height units",
    )
    opacity: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Blend between original (0) and warped (1)",
    )
    strength: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Peak UV displacement magnitude at the ring center",
    )
    speed: float = Field(
        default=0.8,
        ge=0.1,
        le=3.0,
        multiple_of=0.1,
        description="Ring expansion speed in screen-height units per second",
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
        description="Random seed for fallback burst schedule; None derives from clip id",
    )

    _program: moderngl.Program | None = PrivateAttr(default=None)
    _vao: moderngl.VertexArray | None = PrivateAttr(default=None)
    _fps: float = PrivateAttr(default=30.0)
    _aspect: float = PrivateAttr(default=1.7778)
    _spawn_frames: list[int] = PrivateAttr(default_factory=list)

    async def prepare(self, ctx: PrepareContext, _bounds: Rect | None = None) -> None:
        self._fps = max(1.0, float(ctx.job.fps))
        self._aspect = float(ctx.job.width) / max(1.0, float(ctx.job.height))
        self._spawn_frames = _precompute_spawn_frames(
            total_frames=max(ctx.job.total_frames, 0),
            fps=self._fps,
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

        current_frame = ctx.time.frame
        fps = self._fps

        # collect up to MAX_RINGS active rings, most recent first
        ages: list[float] = []
        for spawn_f in reversed(self._spawn_frames):
            if spawn_f > current_frame:
                continue
            age = (current_frame - spawn_f) / fps
            if age * self.speed >= MAX_RADIUS:
                break  # this spawn and all older ones have exited the frame
            ages.append(age)
            if len(ages) >= MAX_RINGS:
                break

        while len(ages) < MAX_RINGS:
            ages.append(-1.0)

        prog = self._program
        ctx.source_texture.use(location=0)
        self._set_uniform(prog, "u_source", 0)
        self._set_uniform(prog, "u_aspect", self._aspect)
        self._set_uniform(prog, "u_strength", float(self.strength))
        self._set_uniform(prog, "u_speed", float(self.speed))
        self._set_uniform(prog, "u_width", float(self.width))
        self._set_uniform(prog, "u_opacity", float(self.opacity))
        self._set_uniform(prog, "u_ring_age_0", ages[0])
        self._set_uniform(prog, "u_ring_age_1", ages[1])
        self._set_uniform(prog, "u_ring_age_2", ages[2])

        assert self._vao is not None
        self._vao.render(moderngl.TRIANGLES)
