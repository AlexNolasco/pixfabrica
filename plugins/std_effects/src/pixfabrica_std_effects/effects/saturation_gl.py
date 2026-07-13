"""Bounds-local GL saturation — luma-preserving color punch."""

from __future__ import annotations

from typing import Any, ClassVar

import moderngl
import numpy as np
from pydantic import Field, PrivateAttr

from pixfabrica_core.clips import ClipCategory, ClipTag, PrepareContext
from pixfabrica_core.composition.effect_def import EffectContext, GLEffect
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
uniform float u_saturation;
in vec2 v_uv;
out vec4 fragColor;
void main() {
    vec4 src = texture(u_source, v_uv);
    float luma = dot(src.rgb, vec3(0.299, 0.587, 0.114));
    vec3 rgb = mix(vec3(luma), src.rgb, u_saturation);
    fragColor = vec4(rgb, src.a);
}
"""

_QUAD = np.array(
    [-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0],
    dtype="f4",
)


class SaturationGL(GLEffect):
    """Adjust color saturation (1 = unchanged, 0 = grayscale, >1 = punch)."""

    effect_type: ClassVar[str] = "std-saturation-gl"
    clip_category: ClassVar[ClipCategory] = ClipCategory.EFFECTS
    clip_tags: ClassVar[list[str]] = [ClipTag.GL]

    saturation: float = Field(
        default=1.35,
        ge=0.0,
        le=3.0,
        multiple_of=0.05,
        description="1 = original, 0 = grayscale, above 1 = more vivid",
    )

    _program: moderngl.Program | None = PrivateAttr(default=None)
    _vao: moderngl.VertexArray | None = PrivateAttr(default=None)

    async def prepare(self, _ctx: PrepareContext, _bounds: Rect | None = None) -> None:
        pass

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
        self._set_uniform(self._program, "u_saturation", self.saturation)
        self._vao.render(moderngl.TRIANGLES)
