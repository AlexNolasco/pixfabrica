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
uniform float u_intensity;
uniform float u_burst_phase;
uniform float u_line_count;
uniform float u_line_width;
uniform float u_opacity;

in vec2 v_uv;
out vec4 fragColor;

const float PI = 3.14159265358979;

void main() {
    vec3 original = texture(u_source, v_uv).rgb;

    if (u_intensity <= 0.0) {
        fragColor = vec4(original, 1.0);
        return;
    }

    // aspect-correct distance and angle from center
    vec2 diff = v_uv - vec2(0.5);
    diff.x *= u_aspect;
    float dist = length(diff);

    float angle_norm = atan(diff.y, diff.x) / (2.0 * PI) + 0.5;  // [0, 1]
    float sector = fract((angle_norm + u_burst_phase) * u_line_count);

    // soft line mask: 0 at sector edges, 1 at sector center
    float from_center = abs(sector - 0.5) * 2.0;  // 0 = on line, 1 = in gap
    float line_mask = 1.0 - smoothstep(u_line_width, u_line_width + 0.08, from_center);

    // inner dead zone so lines don't converge to a hard spike at origin
    float inner = smoothstep(0.05, 0.2, dist);

    float add = line_mask * inner * u_intensity * u_opacity;
    fragColor = vec4(clamp(original + vec3(add), 0.0, 1.0), 1.0);
}
"""

_QUAD = np.array([-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0], dtype="f4")

DECAY_ENVELOPE: tuple[float, ...] = (1.0, 0.6, 0.25, 0.05)
FALLBACK_INTERVAL_MIN_S = 2.0
FALLBACK_INTERVAL_MAX_S = 4.0
AMPLITUDE_GATE = 0.3
AMPLITUDE_SPIKE_DELTA = 0.15


def _passes_sensitivity(amplitude: float, sensitivity: float) -> bool:
    if sensitivity <= 0.0:
        return True
    return amplitude > sensitivity * AMPLITUDE_GATE


def _precompute_speed_envelope(
    *,
    total_frames: int,
    fps: float,
    clip_id: str,
    seed: int | None,
    sensitivity: float,
    bus_select: str | None,
    bus_frames: list[AudioBusFrame] | None,
) -> tuple[np.ndarray, np.ndarray]:
    intensity = np.zeros(total_frames, dtype=np.float32)
    burst_phase = np.zeros(total_frames, dtype=np.float32)

    if total_frames <= 0:
        return intensity, burst_phase

    rng = SeededRandom(seed) if seed is not None else SeededRandom.from_string(clip_id)
    bus_connected = bool((bus_select or "").strip())

    def stamp_burst(start_frame: int, phase: float) -> None:
        for i, decay in enumerate(DECAY_ENVELOPE):
            f = start_frame + i
            if f >= len(intensity):
                break
            if decay >= intensity[f]:
                intensity[f] = decay
                burst_phase[f] = phase

    if bus_connected and bus_frames:
        n = min(total_frames, len(bus_frames))
        bus_has_onsets = any(bus_frames[f].onset for f in range(n))
        if bus_has_onsets:
            for f in range(n):
                af = bus_frames[f]
                if af.onset and _passes_sensitivity(af.amplitude, sensitivity):
                    stamp_burst(f, rng.next())
        else:
            for f in range(1, n):
                af = bus_frames[f]
                delta = af.amplitude - bus_frames[f - 1].amplitude
                if (
                    intensity[f] == 0.0
                    and delta > AMPLITUDE_SPIKE_DELTA
                    and _passes_sensitivity(af.amplitude, sensitivity)
                ):
                    stamp_burst(f, rng.next())
    else:
        frame = int(rng.next() * fps * 0.5)
        while frame < total_frames:
            stamp_burst(frame, rng.next())
            gap_s = FALLBACK_INTERVAL_MIN_S + rng.next() * (
                FALLBACK_INTERVAL_MAX_S - FALLBACK_INTERVAL_MIN_S
            )
            frame += max(1, int(gap_s * fps))

    return intensity, burst_phase


class SpeedLines(AudioVisualMixin, GLPostProcessClip):
    """Onset-triggered radial speed-line burst, white additive.

    Fires on audio onsets when ``bus_select`` is set; falls back to amplitude
    spikes or procedural scheduling without a bus. Each burst rotates the line
    pattern by a random phase so successive hits look distinct. Stack on a
    GLEffectTrack (``std-post-track``), typically after VHS/scanlines and before
    Rain Drops.
    """

    clip_type: ClassVar[str] = "std-speed-lines"
    clip_category: ClassVar[ClipCategory] = ClipCategory.POSTPROCESS
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED, ClipTag.GL]

    line_count: int = Field(
        default=24,
        ge=8,
        le=64,
        description="Number of radial lines",
    )
    line_width: float = Field(
        default=0.4,
        ge=0.05,
        le=0.9,
        multiple_of=0.05,
        description="Line width as a fraction of sector width (0 = invisible, 0.9 = nearly solid)",
    )
    opacity: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Additive brightness scale at full burst intensity",
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
        description="Random seed for burst phase and fallback schedule; None derives from clip id",
    )

    _program: moderngl.Program | None = PrivateAttr(default=None)
    _vao: moderngl.VertexArray | None = PrivateAttr(default=None)
    _aspect: float = PrivateAttr(default=1.7778)
    _intensity: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype=np.float32))
    _burst_phase: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype=np.float32))

    async def prepare(self, ctx: PrepareContext, _bounds: Rect | None = None) -> None:
        self._aspect = float(ctx.job.width) / max(1.0, float(ctx.job.height))
        self._intensity, self._burst_phase = _precompute_speed_envelope(
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
        burst_phase = float(self._burst_phase[f]) if self._burst_phase.size else 0.0

        prog = self._program
        ctx.source_texture.use(location=0)
        self._set_uniform(prog, "u_source", 0)
        self._set_uniform(prog, "u_aspect", self._aspect)
        self._set_uniform(prog, "u_intensity", intensity)
        self._set_uniform(prog, "u_burst_phase", burst_phase)
        self._set_uniform(prog, "u_line_count", float(self.line_count))
        self._set_uniform(prog, "u_line_width", float(self.line_width))
        self._set_uniform(prog, "u_opacity", float(self.opacity))

        assert self._vao is not None
        self._vao.render(moderngl.TRIANGLES)
