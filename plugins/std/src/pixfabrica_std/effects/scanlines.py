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
uniform float u_res_y;
uniform float u_spacing;
uniform float u_intensity;
uniform float u_opacity;

in vec2 v_uv;
out vec4 fragColor;

void main() {
    vec3 original = texture(u_source, v_uv).rgb;

    float row  = floor(v_uv.y * u_res_y / u_spacing);
    float dark = mod(row, 2.0) * u_intensity;
    vec3 scanned = original * (1.0 - dark);

    fragColor = vec4(mix(original, scanned, u_opacity), 1.0);
}
"""

_QUAD = np.array([-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0], dtype="f4")


class Scanlines(GLPostProcessClip):
    """CRT scanline post-processing effect.

    Darkens every other horizontal band to simulate an old CRT or broadcast monitor.
    Place on a GLEffectTrack (``std-post-track``) — one effect row, at most one effect.
    """

    clip_type: ClassVar[str] = "std-scanlines"
    clip_category: ClassVar[ClipCategory] = ClipCategory.POSTPROCESS
    clip_tags: ClassVar[list[str]] = [ClipTag.GL]

    spacing: float = Field(
        default=2.0,
        ge=1.0,
        le=16.0,
        multiple_of=1.0,
        description="Pixels per scanline band (2 = every other row, 4 = every 4 rows, etc.)",
    )
    intensity: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Darkness of the dim bands (0 = invisible, 1 = fully black)",
    )
    opacity: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Blend between original (0) and scanlined (1)",
    )

    _program: moderngl.Program | None = PrivateAttr(default=None)
    _vao: moderngl.VertexArray | None = PrivateAttr(default=None)
    _res_y: float = PrivateAttr(default=0.0)

    async def prepare(self, ctx: PrepareContext, _bounds: Rect | None = None) -> None:
        self._res_y = float(ctx.job.height)

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
        self._set_uniform(prog, "u_res_y", self._res_y)
        self._set_uniform(prog, "u_spacing", self.spacing)
        self._set_uniform(prog, "u_intensity", self.intensity)
        self._set_uniform(prog, "u_opacity", self.opacity)

        assert self._vao is not None
        self._vao.render(moderngl.TRIANGLES)
