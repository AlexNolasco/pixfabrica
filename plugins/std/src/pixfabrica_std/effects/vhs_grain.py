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
uniform float u_time;
uniform float u_strength;
uniform float u_grain;
uniform float u_opacity;

in vec2 v_uv;
out vec4 fragColor;

float random1d(float dt) {
    return fract(sin(mod(dt, 3.14)) * 43758.5453);
}

float noise1d(float value) {
    float i = floor(value);
    float f = fract(value);
    return mix(random1d(i), random1d(i + 1.0), smoothstep(0.0, 1.0, f));
}

float random2d(vec2 co) {
    float dt = dot(co, vec2(12.9898, 78.233));
    return fract(sin(mod(dt, 3.14)) * 43758.5453);
}

void main() {
    float strength = (0.3 + 0.7 * noise1d(0.3 * u_time)) * u_strength;
    float jump = 500.0 * floor(0.3 * u_strength * (u_time + noise1d(u_time)));

    vec2 uv = v_uv;
    uv.y += 0.2 * strength * (noise1d(5.0  * v_uv.y + 2.0 * u_time + jump) - 0.5);
    uv.x += 0.1 * strength * (noise1d(100.0 * strength * uv.y + 3.0 * u_time + jump) - 0.5);
    uv = clamp(uv, 0.0, 1.0);

    vec3 original = texture(u_source, v_uv).rgb;
    vec3 warped   = texture(u_source, uv).rgb;

    // Additive grain noise
    warped += vec3(5.0 * u_grain * strength * (random2d(v_uv + 1.133001 * vec2(u_time, 1.13)) - 0.5));
    warped  = clamp(warped, 0.0, 1.0);

    // Blend processed vs original; always output full alpha so the blit replaces the frame
    fragColor = vec4(mix(original, warped, u_opacity), 1.0);
}
"""

_QUAD = np.array([-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0], dtype="f4")


class VHSGrain(GLPostProcessClip):
    """Grainy old-TV / VHS post-processing effect.

    Applies UV jitter (tape warp) and additive grain noise to the full composited frame.
    Place on a GLEffectTrack (``std-post-track``) so it processes the entire composition
    up to that row in the track list.
    """

    clip_type: ClassVar[str] = "std-vhs-grain"
    clip_category: ClassVar[ClipCategory] = ClipCategory.POSTPROCESS
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED, ClipTag.GL]

    strength: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="VHS warp + tape-jump strength",
    )
    grain: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="White noise grain overlay amount",
    )
    opacity: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Blend between original (0) and fully processed (1)",
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
        self._set_uniform(prog, "u_time", ctx.time.t)
        self._set_uniform(prog, "u_strength", self.strength)
        self._set_uniform(prog, "u_grain", self.grain)
        self._set_uniform(prog, "u_opacity", self.opacity)

        assert self._vao is not None
        self._vao.render(moderngl.TRIANGLES)
