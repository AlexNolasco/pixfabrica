from __future__ import annotations

from typing import Any, ClassVar, Literal

import moderngl
import numpy as np
from pydantic import Field, PrivateAttr

from pixfabrica_core.clips import ClipCategory, ClipGL, ClipTag, PrepareContext, RenderContext
from pixfabrica_core.graphics import Rect
from pixfabrica_core.theme.color import Color, ColorToken, color_field, resolve_color

_VERT = """
#version 330 core
in vec2 in_vert;
void main() { gl_Position = vec4(in_vert, 0.0, 1.0); }
"""

_FRAG = """
#version 330 core

uniform vec2  u_res;
uniform vec2  u_origin;
uniform float u_canvas_h;
uniform float u_t;

uniform vec3  u_color;
uniform float u_thickness;
uniform float u_tail_length; 
uniform float u_speed;
uniform float u_dir;
uniform float u_inset;
uniform float u_opacity;
uniform float u_core_white;

out vec4 frag_color;

vec2 get_pos_from_1d(float p, float w, float h) {
    if (p < 2.0 * w) return vec2(p - w, h);
    p -= 2.0 * w;
    if (p < 2.0 * h) return vec2(w, h - p);
    p -= 2.0 * h;
    if (p < 2.0 * w) return vec2(w - p, -h);
    p -= 2.0 * w;
    return vec2(-w, -h + p);
}

void main() {
    // 1. Coordinate Space
    float px = gl_FragCoord.x - u_origin.x;
    float py = (u_canvas_h - gl_FragCoord.y) - u_origin.y;
    vec2 local_px = vec2(px, py);
    vec2 center = u_res * 0.5;
    
    vec2 p = local_px - center;
    float w = max((u_res.x * 0.5) - u_inset, 0.1);
    float h = max((u_res.y * 0.5) - u_inset, 0.1);
    
    // 2. Base Rectangle SDF
    vec2 abs_p = abs(p);
    vec2 d = abs_p - vec2(w, h);
    float dist_to_fill = length(max(d, 0.0)) + min(max(d.x, d.y), 0.0);
    float border_dist = abs(dist_to_fill);
    
    // 3. 1D Perimeter Mapping
    float dist_x = w - abs_p.x;
    float dist_y = h - abs_p.y;
    
    float pos = 0.0;
    if (dist_y < dist_x) {
        if (p.y > 0.0) pos = p.x + w; 
        else pos = 2.0*w + 2.0*h + (w - p.x); 
    } else {
        if (p.x > 0.0) pos = 2.0*w + (h - p.y); 
        else pos = 4.0*w + 2.0*h + (p.y + h); 
    }
    
    float perimeter = 4.0 * (w + h);
    
    float head_pos = mod(u_t * (u_speed * u_dir), perimeter);
    
    // 4. Normalized Tail Calculation
    // FLIPPED: The tail now calculates distance based on the vector of travel
    float diff = mod((head_pos - pos) * u_dir, perimeter);
    
    float actual_max_dim = max(w * 2.0, h * 2.0); 
    float tail_px = max(u_tail_length * actual_max_dim, 1.0); 
    
    float normalized_diff = clamp(diff / tail_px, 0.0, 1.0);
    float tail_intensity = pow(1.0 - normalized_diff, 1.5);
    
    float cross_intensity = exp(-border_dist * border_dist * (1.0 / max(u_thickness * u_thickness, 1.0)));
    
    // 5. Perfect Round Head
    vec2 head_xy = get_pos_from_1d(head_pos, w, h);
    float head_dist = length(p - head_xy);
    float head_glow = exp(-head_dist * head_dist * (2.0 / max(u_thickness * u_thickness, 1.0)));
    
    // 6. Output
    float energy = max(tail_intensity * cross_intensity, head_glow);
    float alpha = clamp(energy * u_opacity, 0.0, 1.0);
    
    vec3 final_color = mix(u_color, vec3(1.0), alpha * u_core_white);
    frag_color = vec4(final_color * alpha, alpha);
}
"""

_QUAD = np.array([-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0], dtype="f4")


class BorderPlasmaGL(ClipGL):
    """GPU-accelerated comet that perfectly traces a rectangular bounds perimeter."""

    clip_type: ClassVar[str] = "std-border-plasma-gl"
    clip_category: ClassVar[ClipCategory] = ClipCategory.EFFECTS
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED, ClipTag.LOOP, ClipTag.GL, ClipTag.GLOW]

    color: ColorToken | Color = color_field(ColorToken.SECONDARY)

    # Appearance
    thickness: float = Field(
        default=4.0, ge=0.0, le=16, multiple_of=0.1, description="Comet stroke thickness in pixels"
    )
    tail_length: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Tail length as fraction of the longest dimension",
    )
    core_white_blend: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Blend toward white at the comet head (0=color only, 1=full white)",
    )

    # Motion
    speed: float = Field(
        default=400.0,
        ge=0.0,
        multiple_of=1.0,
        le=1600,
        description="Travel speed in px/s at output resolution along the perimeter",
    )
    direction: Literal["cw", "ccw"] = Field(
        default="cw", description="Travel direction: clockwise or counter-clockwise"
    )

    # Layout
    opacity: float = Field(
        default=1.0, ge=0.0, le=1.0, multiple_of=0.1, description="Overall layer opacity"
    )
    inset: float = Field(
        default=0.0,
        ge=0.0,
        multiple_of=1.0,
        le=255.0,
        description="Inset from bounds edge in pixels",
    )

    # Precomputed Bounds
    _canvas_w: float = PrivateAttr(default=0.0)
    _canvas_h: float = PrivateAttr(default=0.0)
    _bounds_x: float = PrivateAttr(default=0.0)
    _bounds_y: float = PrivateAttr(default=0.0)
    _bounds_w: float = PrivateAttr(default=0.0)
    _bounds_h: float = PrivateAttr(default=0.0)

    # GL Objects
    _program: moderngl.Program | None = PrivateAttr(default=None)
    _vao: moderngl.VertexArray | None = PrivateAttr(default=None)

    async def prepare(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        b = bounds or Rect(0, 0, ctx.job.width, ctx.job.height)
        self._canvas_w = float(ctx.job.width)
        self._canvas_h = float(ctx.job.height)
        self._bounds_x = float(b.x)
        self._bounds_y = float(b.y)
        self._bounds_w = float(b.width)
        self._bounds_h = float(b.height)

    def _set_uniform(self, prog: moderngl.Program, name: str, value: Any) -> None:
        if name in prog:
            member = prog[name]
            if isinstance(member, moderngl.Uniform):
                member.value = value

    def draw(self, ctx: RenderContext) -> None:
        gl: moderngl.Context = ctx.canvas

        if self._program is None:
            self._program = gl.program(vertex_shader=_VERT, fragment_shader=_FRAG)
            vbo = gl.buffer(_QUAD.tobytes())
            self._vao = gl.simple_vertex_array(self._program, vbo, "in_vert")

        prog = self._program

        # 1. Base Uniforms
        self._set_uniform(prog, "u_res", (self._bounds_w, self._bounds_h))
        self._set_uniform(prog, "u_origin", (self._bounds_x, self._bounds_y))
        self._set_uniform(prog, "u_canvas_h", self._canvas_h)
        self._set_uniform(prog, "u_t", ctx.time.t)

        # 2. Comet Uniforms
        r, g, b, _ = resolve_color(self.color, ctx.job.colors).rgba
        self._set_uniform(prog, "u_color", (r, g, b))
        self._set_uniform(prog, "u_thickness", self.thickness)
        self._set_uniform(prog, "u_tail_length", self.tail_length)

        self._set_uniform(prog, "u_speed", ctx.job.scale_output_px(self.speed))

        # Translate the string literal to a math multiplier
        direction_multiplier = 1.0 if self.direction == "cw" else -1.0
        self._set_uniform(prog, "u_dir", direction_multiplier)

        self._set_uniform(prog, "u_core_white", self.core_white_blend)
        self._set_uniform(prog, "u_opacity", self.opacity)
        self._set_uniform(prog, "u_inset", self.inset)

        # 3. Scissor and Render
        bnd = ctx.bounds
        gl.scissor = (
            int(self._bounds_x),
            int(ctx.job.height - self._bounds_y - bnd.height),
            int(self._bounds_w),
            int(bnd.height),
        )

        assert self._vao is not None
        self._vao.render(moderngl.TRIANGLES)

        gl.scissor = None
