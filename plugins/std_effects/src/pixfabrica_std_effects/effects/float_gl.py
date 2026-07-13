"""Bounds-local GL float — gentle vertical sine bob."""

from __future__ import annotations

import math
from typing import Any, ClassVar

import moderngl
import numpy as np
from pydantic import Field, PrivateAttr

from pixfabrica_core.clips import ClipCategory, ClipTag, PrepareContext
from pixfabrica_core.composition.effect_def import EffectContext, GLEffect, set_gl_src_uv_uniforms
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
uniform float u_amplitude;
uniform float u_time;
uniform float u_period;
uniform float u_phase;
uniform float u_wave_at_origin;
uniform vec2 u_src_scale;
uniform vec2 u_src_bias;

in vec2 v_uv;
out vec4 fragColor;

const float PI = 3.14159265358979;

void main() {
    float wave = sin(2.0 * PI * (u_time / u_period + u_phase));
    float bob = u_amplitude * (wave - u_wave_at_origin);
    vec2 uv = v_uv;
    uv.y += bob;
    vec2 src_uv = uv * u_src_scale + u_src_bias;

    if (src_uv.x < 0.0 || src_uv.x > 1.0 || src_uv.y < 0.0 || src_uv.y > 1.0) {
        fragColor = vec4(0.0);
        return;
    }

    fragColor = texture(u_source, src_uv);
}
"""

_QUAD = np.array(
    [-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0],
    dtype="f4",
)


class FloatGL(GLEffect):
    """Gentle vertical sine bob — zero displacement at the track origin time."""

    uv_margin: ClassVar[float] = 0.02
    effect_type: ClassVar[str] = "std-float-gl"
    clip_category: ClassVar[ClipCategory] = ClipCategory.EFFECTS
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED, ClipTag.GL]

    amplitude: float = Field(
        default=0.05,
        ge=0.01,
        le=0.15,
        multiple_of=0.01,
        description="Peak vertical travel as a fraction of clip height",
    )
    period: float = Field(
        default=2.5,
        ge=1.5,
        le=8.0,
        multiple_of=0.5,
        description="Seconds for one full up-down cycle",
    )

    _program: moderngl.Program | None = PrivateAttr(default=None)
    _vao: moderngl.VertexArray | None = PrivateAttr(default=None)
    _phase: float = PrivateAttr(default=0.0)
    _time_origin: float = PrivateAttr(default=0.0)

    async def prepare(self, ctx: PrepareContext, _bounds: Rect | None = None) -> None:
        self._phase = SeededRandom.from_string(self.id).next()
        parent = ctx.parent_clip
        raw_start = getattr(parent, "start", 0.0) if parent is not None else 0.0
        self._time_origin = float(raw_start or 0.0)

    def _set_uniform(self, prog: moderngl.Program, name: str, value: Any) -> None:
        if name in prog:
            member = prog[name]
            if isinstance(member, moderngl.Uniform):
                member.value = value

    def apply(self, ctx: EffectContext) -> None:
        source = ctx.source
        target = ctx.target
        if source is None:
            return

        period = max(float(self.period), 1e-3)
        phase = float(self._phase)
        wave_at_origin = math.sin(2.0 * math.pi * (self._time_origin / period + phase))

        gl: moderngl.Context = target.ctx
        if self._program is None:
            self._program = gl.program(vertex_shader=_VERT, fragment_shader=_FRAG)
            vbo = gl.buffer(_QUAD.tobytes())
            self._vao = gl.simple_vertex_array(self._program, vbo, "in_vert")

        assert self._program is not None
        assert self._vao is not None
        target.use()
        source.use(location=0)
        self._set_uniform(self._program, "u_source", 0)
        self._set_uniform(self._program, "u_amplitude", float(self.amplitude))
        self._set_uniform(self._program, "u_time", float(ctx.time.t))
        self._set_uniform(self._program, "u_period", period)
        self._set_uniform(self._program, "u_phase", phase)
        self._set_uniform(self._program, "u_wave_at_origin", wave_at_origin)
        set_gl_src_uv_uniforms(self._program, ctx)
        self._vao.render(moderngl.TRIANGLES)
