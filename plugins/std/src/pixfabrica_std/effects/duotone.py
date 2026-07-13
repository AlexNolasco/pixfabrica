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
uniform vec3 u_shadow;
uniform vec3 u_highlight;
uniform float u_opacity;

in vec2 v_uv;
out vec4 fragColor;

void main() {
    vec3 original = texture(u_source, v_uv).rgb;
    float luma = dot(original, vec3(0.2126, 0.7152, 0.0722));
    vec3 duotone = mix(u_shadow, u_highlight, luma);
    fragColor = vec4(mix(original, duotone, u_opacity), 1.0);
}
"""

_QUAD = np.array([-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0], dtype="f4")


class Duotone(GLPostProcessClip):
    """Two-color grade that maps pixel luminance to a shadow/highlight color pair.

    Dark areas take ``shadow_color`` (default: theme primary), bright areas take
    ``highlight_color`` (default: theme accent). Place on a GLEffectTrack
    (``std-post-track``) to grade the entire composited frame.
    """

    clip_type: ClassVar[str] = "std-duotone"
    clip_category: ClassVar[ClipCategory] = ClipCategory.POSTPROCESS
    clip_tags: ClassVar[list[str]] = [ClipTag.GL]

    shadow_color: ColorToken | Color = color_field(ColorToken.PRIMARY)
    highlight_color: ColorToken | Color = color_field(ColorToken.ACCENT)
    opacity: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Blend between original (0) and fully graded (1)",
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

        sr, sg, sb, _ = resolve_color(self.shadow_color, ctx.job.colors).rgba
        hr, hg, hb, _ = resolve_color(self.highlight_color, ctx.job.colors).rgba
        self._set_uniform(prog, "u_shadow", (sr, sg, sb))
        self._set_uniform(prog, "u_highlight", (hr, hg, hb))
        self._set_uniform(prog, "u_opacity", self.opacity)

        assert self._vao is not None
        self._vao.render(moderngl.TRIANGLES)
