"""Bounds-local GL colorize — luminance mapped to a theme tint."""

from __future__ import annotations

from typing import Any, ClassVar

import moderngl
import numpy as np
from pydantic import Field, PrivateAttr

from pixfabrica_core.clips import ClipCategory, ClipTag, PrepareContext
from pixfabrica_core.composition.effect_def import EffectContext, GLEffect
from pixfabrica_core.graphics import Rect
from pixfabrica_core.theme.color import Color, ColorToken, color_field, resolve_color

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
uniform vec3 u_tint;
uniform float u_strength;
in vec2 v_uv;
out vec4 fragColor;
void main() {
    vec4 src = texture(u_source, v_uv);
    float luma = dot(src.rgb, vec3(0.299, 0.587, 0.114));
    vec3 colorized = u_tint * luma;
    vec3 rgb = mix(src.rgb, colorized, u_strength);
    fragColor = vec4(rgb, src.a);
}
"""

_QUAD = np.array(
    [-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0],
    dtype="f4",
)


class ColorizeGL(GLEffect):
    """Wash clip output with a theme tint (luminance → color)."""

    effect_type: ClassVar[str] = "std-colorize-gl"
    clip_category: ClassVar[ClipCategory] = ClipCategory.EFFECTS
    clip_tags: ClassVar[list[str]] = [ClipTag.GL]

    tint: ColorToken | Color = color_field(ColorToken.ACCENT)
    strength: float = Field(
        default=0.65,
        ge=0.0,
        le=1.0,
        multiple_of=0.05,
        description="Blend between original (0) and tinted (1)",
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

        tr, tg, tb, _ = resolve_color(self.tint, ctx.job.colors).rgba

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
        self._set_uniform(self._program, "u_tint", (tr, tg, tb))
        self._set_uniform(self._program, "u_strength", self.strength)
        self._vao.render(moderngl.TRIANGLES)
