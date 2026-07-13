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
uniform float u_size;
uniform float u_opacity;

in vec2 v_uv;
out vec4 fragColor;

void main() {
    vec2 blocks   = floor(v_uv * u_resolution / u_size) * u_size + u_size * 0.5;
    vec3 pixelated = texture(u_source, blocks / u_resolution).rgb;
    vec3 original  = texture(u_source, v_uv).rgb;
    fragColor = vec4(mix(original, pixelated, u_opacity), 1.0);
}
"""

_QUAD = np.array([-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0], dtype="f4")


class Pixelate(GLPostProcessClip):
    """Pixelate / mosaic post-processing effect.

    Snaps each pixel to the centre of its block, giving a retro low-res look.
    Place on a GLEffectTrack (``std-post-track``) — one effect row, at most one effect.
    """

    clip_type: ClassVar[str] = "std-pixelate"
    clip_category: ClassVar[ClipCategory] = ClipCategory.POSTPROCESS
    clip_tags: ClassVar[list[str]] = [ClipTag.GL]

    size: float = Field(
        default=0.015,
        ge=0.002,
        le=0.5,
        multiple_of=0.001,
        description="Block size as a fraction of frame height (0.015 ≈ 8px on 540p, 16px on 1080p)",
    )
    opacity: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Blend between original (0) and pixelated (1)",
    )

    _program: moderngl.Program | None = PrivateAttr(default=None)
    _vao: moderngl.VertexArray | None = PrivateAttr(default=None)
    _res: tuple[float, float] = PrivateAttr(default=(0.0, 0.0))
    _size_px: float = PrivateAttr(default=0.0)

    async def prepare(self, ctx: PrepareContext, _bounds: Rect | None = None) -> None:
        self._res = (float(ctx.job.width), float(ctx.job.height))
        self._size_px = self.size * ctx.job.height

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
        self._set_uniform(prog, "u_size", self._size_px)
        self._set_uniform(prog, "u_opacity", self.opacity)

        assert self._vao is not None
        self._vao.render(moderngl.TRIANGLES)
