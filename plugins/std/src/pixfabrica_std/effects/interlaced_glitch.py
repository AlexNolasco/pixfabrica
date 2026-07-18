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

# Original shader by Msama: https://www.shadertoy.com/user/Msama
# Shadertoy default license: CC BY-NC-SA 3.0

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
uniform vec3 u_resolution;
uniform float u_time;
uniform float u_speed;
uniform int u_directions;
uniform int u_samples;
uniform float u_opacity;

in vec2 v_uv;
out vec4 fragColor;

float rand(vec2 co) {
    return fract(sin(dot(co, vec2(12.9898, 78.233))) * 43758.5453);
}

vec4 interlace(vec2 co, vec4 col) {
    if (int(co.y) % 3 == 0) {
        return col * ((sin(u_time * u_speed * 4.0) * 0.1) + 0.75)
            + (rand(vec2(u_time * u_speed, u_time * u_speed)) * 0.05);
    }
    return col;
}

vec4 apply_glitch(vec2 frag_coord) {
    bool normal = false;
    float time = u_time * u_speed;

    vec2 uv = frag_coord / u_resolution.xy;

    vec2 uvneg = vec2(
        frag_coord.x / u_resolution.x
            - (rand(vec2(frag_coord.y + time * 0.0001, 0.0)) * 0.06),
        frag_coord.y / u_resolution.y
    );
    vec2 uvnegR = vec2(
        uvneg.x + (rand(vec2(time * 0.005, u_resolution.x)) * 0.1),
        uvneg.y
    );
    vec2 uvnegG = vec2(
        uvneg.x + (rand(vec2(time * 0.005, u_resolution.y)) * 0.1),
        uvneg.y
    );
    vec2 uvnegB = vec2(
        uvneg.x + (rand(vec2(time * 0.005, u_resolution.z)) * 0.1),
        uvneg.y
    );

    vec2 uvpos = vec2(
        frag_coord.x / u_resolution.x
            + (rand(vec2(frag_coord.y + time * 0.0001, 0.0)) * 0.03),
        frag_coord.y / u_resolution.y
    );
    vec2 uvposR = vec2(
        uvpos.x + (rand(vec2(time * 0.005, u_resolution.x)) * 0.1),
        uvpos.y
    );
    vec2 uvposG = vec2(
        uvpos.x + (rand(vec2(time * 0.005, u_resolution.y)) * 0.1),
        uvpos.y
    );
    vec2 uvposB = vec2(
        uvpos.x + (rand(vec2(time * 0.005, u_resolution.z)) * 0.1),
        uvpos.y
    );

    vec2 uvNormal = vec2(
        frag_coord.x / u_resolution.x
            + (rand(vec2(frag_coord.y + time * 0.001, 0.0)) * 0.006),
        frag_coord.y / u_resolution.y
    );

    float displace = 0.005;
    if (rand(vec2(time * 0.001, u_resolution.x)) > 0.8) {
        displace = rand(vec2(time * 0.1, u_resolution.y)) / 10.0 + (uv.y / 5.0);
    }

    vec2 uvGlitch = vec2(
        uv.x + (rand(vec2(time * 0.005, u_resolution.x)) * displace),
        uv.y
    );
    float startGlitch = rand(vec2(time * 0.004, u_resolution.y));
    float startGlitch2 = rand(vec2(time * 0.004, u_resolution.x));

    float Pi = 6.28318530718;
    float dir = float(u_directions);
    float qual = float(u_samples);
    float size = rand(vec2(time, frag_coord.y)) * 20.0;
    vec2 Radius = size / u_resolution.xy;

    vec4 original = texture(u_source, uv);
    vec4 Color = original;

    for (int direction_index = 0; direction_index < 16; ++direction_index) {
        if (direction_index >= u_directions) {
            break;
        }
        float d = float(direction_index) * Pi / dir;
        for (int sample_index = 1; sample_index <= 10; ++sample_index) {
            if (sample_index > u_samples) {
                break;
            }
            float i = float(sample_index) / qual;
            float sample_y = uv.y + sin(d) * Radius.y * i;
            vec2 radial_offset = vec2(cos(d), sin(d)) * Radius * i;

            if (
                sample_y < startGlitch + 0.02
                && sample_y
                    > startGlitch - rand(vec2(time * 0.002, u_resolution.y)) / 5.0
            ) {
                Color.r += texture(u_source, uvnegR + radial_offset).r;
            } else if (
                sample_y < startGlitch + 0.04
                && sample_y
                    > startGlitch - rand(vec2(time * 0.002, u_resolution.x)) / 5.2
            ) {
                Color.r += texture(u_source, uvposR + radial_offset).r;
            }

            if (
                sample_y < startGlitch
                && sample_y
                    > startGlitch - rand(vec2(time * 0.002, u_resolution.y)) / 2.0
            ) {
                Color.g += texture(u_source, uvnegG + radial_offset).g;
            } else if (
                sample_y < startGlitch2
                && sample_y
                    > startGlitch2 - rand(vec2(time * 0.002, u_resolution.x)) / 3.0
            ) {
                Color.g += texture(u_source, uvposG + radial_offset).g;
            }

            if (
                sample_y < startGlitch + 0.01
                && sample_y
                    > startGlitch - rand(vec2(time * 0.002, u_resolution.y)) / 4.0
            ) {
                Color.b += texture(u_source, uvnegB + radial_offset).b;
            } else if (
                sample_y < startGlitch2 + 0.03
                && sample_y
                    > startGlitch2 - rand(vec2(time * 0.002, u_resolution.x)) / 5.4
            ) {
                Color.b += texture(u_source, uvposB + radial_offset).b;
            } else {
                Color.g += texture(
                    u_source,
                    vec2(
                        (uvNormal + radial_offset + displace).x,
                        uvNormal.y
                            + rand(vec2(time * 0.001, u_resolution.y)) * 0.075
                    )
                ).g;
                Color.b += texture(u_source, uvGlitch).b;
                Color.r += texture(u_source, uvGlitch + radial_offset).r;
                normal = true;
            }
        }
    }

    Color /= max(qual * dir * (145.0 / 160.0), 1.0);
    if (normal) {
        return interlace(frag_coord, Color);
    }

    // The source shader overwrites its interlaced value on this path.
    return Color;
}

void main() {
    vec4 original = texture(u_source, v_uv);
    vec4 glitched = apply_glitch(gl_FragCoord.xy);
    fragColor = vec4(mix(original.rgb, glitched.rgb, u_opacity), 1.0);
}
"""

_QUAD = np.array(
    [-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0],
    dtype="f4",
)


class InterlacedGlitch(GLPostProcessClip):
    """Dense interlaced chromatic smear based on Msama's Shadertoy shader.

    Preserves the source shader's full 16 by 10 sampling pattern and timing.
    Place on a GLEffectTrack (``std-post-track``).
    """

    clip_type: ClassVar[str] = "std-interlaced-glitch"
    clip_license: ClassVar[str] = "CC-BY-NC-SA-3.0"
    clip_category: ClassVar[ClipCategory] = ClipCategory.POSTPROCESS
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED, ClipTag.GL]

    speed: float = Field(
        default=1.0,
        ge=0.1,
        le=3.0,
        multiple_of=0.1,
        description="Animation speed multiplier",
    )
    directions: int = Field(
        default=16,
        ge=4,
        le=16,
        multiple_of=2,
        description="Angular sample directions; lower values render faster",
    )
    samples: int = Field(
        default=10,
        ge=2,
        le=10,
        multiple_of=1,
        description="Radial samples per direction; lower values render faster",
    )
    opacity: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Blend between original (0) and glitched (1)",
    )

    _program: moderngl.Program | None = PrivateAttr(default=None)
    _vao: moderngl.VertexArray | None = PrivateAttr(default=None)
    _res: tuple[float, float, float] = PrivateAttr(default=(0.0, 0.0, 1.0))

    async def prepare(self, ctx: PrepareContext, _bounds: Rect | None = None) -> None:
        self._res = (float(ctx.job.width), float(ctx.job.height), 1.0)

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
        self._set_uniform(prog, "u_time", float(ctx.time.t))
        self._set_uniform(prog, "u_speed", float(self.speed))
        self._set_uniform(prog, "u_directions", int(self.directions))
        self._set_uniform(prog, "u_samples", int(self.samples))
        self._set_uniform(prog, "u_opacity", float(self.opacity))

        assert self._vao is not None
        self._vao.render(moderngl.TRIANGLES)
