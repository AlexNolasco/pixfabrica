from __future__ import annotations

from typing import Any, ClassVar

import moderngl
import numpy as np
from pydantic import Field, PrivateAttr

from pixfabrica_core.clips import (
    ClipCategory,
    ClipTag,
    GLPostProcessClip,
    PrepareContext,
    RenderContext,
)
from pixfabrica_core.graphics import Rect

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
uniform float u_strength;
uniform float u_radius;
uniform float u_feather;
uniform float u_opacity;

in vec2 v_uv;
out vec4 fragColor;

void main() {
    vec3 original = texture(u_source, v_uv).rgb;

    vec2 p = v_uv - 0.5;
    float aspect = u_resolution.x / u_resolution.y;
    p.x *= aspect;
    float dist = length(p);
    float corner = length(vec2(aspect * 0.5, 0.5));
    float nd = dist / max(corner, 1e-5);

    float darken = smoothstep(u_radius, u_radius + u_feather, nd);
    vec3 vignetted = original * (1.0 - u_strength * darken);

    fragColor = vec4(mix(original, vignetted, u_opacity), 1.0);
}
"""

_QUAD = np.array([-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0], dtype="f4")

FEATHER = 0.15


class Vignette(GLPostProcessClip):
    """Radial corner darkening post-processing effect.

    Stack last — after Rain Drops — on a GLEffectTrack (``std-post-track``).
    """

    clip_type: ClassVar[str] = "std-vignette"
    clip_category: ClassVar[ClipCategory] = ClipCategory.POSTPROCESS
    clip_tags: ClassVar[list[str]] = [ClipTag.GL]

    strength: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.05,
        description="Corner darkening amount",
    )
    radius: float = Field(
        default=0.70,
        ge=0.0,
        le=0.85,
        multiple_of=0.05,
        description="Inner clear zone as fraction of distance from center to corner",
    )
    opacity: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Blend between original (0) and vignetted (1)",
    )

    _program: moderngl.Program | None = PrivateAttr(default=None)
    _vao: moderngl.VertexArray | None = PrivateAttr(default=None)
    _res: tuple[float, float] = PrivateAttr(default=(0.0, 0.0))

    async def prepare(self, ctx: PrepareContext, _bounds: Rect | None = None) -> None:
        self._res = (float(ctx.job.width), float(ctx.job.height))

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

        prog = self._program
        ctx.source_texture.use(location=0)
        self._set_uniform(prog, "u_source", 0)
        self._set_uniform(prog, "u_resolution", self._res)
        self._set_uniform(prog, "u_strength", float(self.strength))
        self._set_uniform(prog, "u_radius", float(self.radius))
        self._set_uniform(prog, "u_feather", FEATHER)
        self._set_uniform(prog, "u_opacity", float(self.opacity))

        assert self._vao is not None
        self._vao.render(moderngl.TRIANGLES)
