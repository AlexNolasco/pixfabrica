from __future__ import annotations

import math
from typing import Any, ClassVar, Literal, cast

import moderngl
import numpy as np
from pydantic import Field, PrivateAttr

from pixfabrica_core.clips import ClipCategory, ClipGL, ClipTag, PrepareContext, RenderContext
from pixfabrica_core.graphics import Rect
from pixfabrica_core.random import SeededRandom
from pixfabrica_core.theme.color import Color, ColorToken, color_field, resolve_color
from pixfabrica_std.tilt import (
    ANGLE_BAND_DESC,
    ANGLE_BAND_SKEW_MAX,
    ANGLE_BAND_SKEW_MIN,
    band_left_center_y,
    band_skew_px,
)

_VERT = """
#version 330 core
in vec2 in_vert;
void main() { gl_Position = vec4(in_vert, 0.0, 1.0); }
"""

_FRAG = """
#version 330 core

uniform vec2  u_res;      // bounds size (width, height)
uniform vec2  u_origin;   // bounds top-left in canvas space (top-down px)
uniform float u_canvas_h; // full canvas height (for gl_FragCoord.y conversion)
uniform float u_t;
uniform vec3  u_color;
uniform float u_band_center_y; // band center Y at bounds-local x=0 (top-down px)
uniform float u_skew_px;
uniform int   u_count;
uniform float u_line_w;
uniform float u_speed;
uniform float u_opacity;
uniform float u_glow;
uniform float u_base_ys[50];
uniform float u_period;
uniform float u_spacing;
uniform float u_half_len;
uniform float u_dx;
uniform float u_dy;
uniform float u_nx;
uniform float u_ny;
uniform int   u_right;
uniform float u_band_h;

out vec4 frag_color;

void main() {
    // Convert fragment coord to bounds-local space (top-left origin).
    float px = gl_FragCoord.x - u_origin.x;
    float py = (u_canvas_h - gl_FragCoord.y) - u_origin.y;

    float slope = u_skew_px / u_res.x;
    // Match Skia sweep_lines: centers slide along the tilted band diagonal.
    float band_cy  = u_band_center_y - slope * px;
    float band_half = u_band_h * u_res.y * 0.5;

    if (abs(py - band_cy) > band_half) {
        frag_color = vec4(0.0);
        return;
    }

    float travel = mod(u_t * u_speed, u_period);
    float accum  = 0.0;

    for (int i = 0; i < u_count; i++) {
        float x_pos;
        if (u_right == 0) {
            x_pos = mod(float(i) * u_spacing + travel, u_period) - u_half_len;
        } else {
            x_pos = u_res.x + u_half_len - mod(float(i) * u_spacing + travel, u_period);
        }

        float cx = x_pos;
        float cy = u_base_ys[i] - slope * x_pos;

        // Capsule distance: project onto segment, clamp, then measure true distance.
        // Moving a line along its own axis leaves perpendicular distance unchanged —
        // capsule distance does change as the endpoints sweep past, giving visible motion.
        float along  = (px - cx) * u_dx + (py - cy) * u_dy;
        float clamped = clamp(along, -u_half_len, u_half_len);
        float npx = cx + clamped * u_dx;
        float npy = cy + clamped * u_dy;
        float dist = length(vec2(px - npx, py - npy));

        float core = exp(-0.5 * pow(dist / max(u_line_w, 0.5), 2.0));
        float halo = u_glow > 0.0 ? 0.5 * exp(-0.5 * pow(dist / u_glow, 2.0)) : 0.0;

        accum += core + halo;
    }

    float alpha = clamp(accum * u_opacity, 0.0, 1.0);
    frag_color = vec4(u_color * alpha, alpha);
}
"""

_QUAD = np.array(
    [
        -1.0,
        -1.0,
        1.0,
        -1.0,
        -1.0,
        1.0,
        -1.0,
        1.0,
        1.0,
        -1.0,
        1.0,
        1.0,
    ],
    dtype="f4",
)


class SweepLinesGL(ClipGL):
    """GPU sweep lines — Gaussian glow is free (per-pixel falloff, no blur pass)."""

    clip_type: ClassVar[str] = "std-sweep-lines-gl"
    clip_category: ClassVar[ClipCategory] = ClipCategory.EFFECTS
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED, ClipTag.LOOP, ClipTag.GL]

    color: ColorToken | Color = color_field(ColorToken.NEUTRAL)
    offset_y: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Band center as fraction of bounds height",
    )
    band_height: float = Field(
        default=0.15,
        ge=0.01,
        le=1.0,
        multiple_of=0.01,
        description="Band thickness as fraction of bounds height",
    )
    angle: float = Field(
        default=6.0,
        ge=ANGLE_BAND_SKEW_MIN,
        le=ANGLE_BAND_SKEW_MAX,
        multiple_of=1.0,
        description=ANGLE_BAND_DESC,
    )
    opacity: float = Field(
        default=0.4, ge=0.0, le=1.0, multiple_of=0.1, description="Overall layer opacity"
    )
    line_count: int = Field(
        default=3, ge=1, le=50, multiple_of=1, description="Number of sweeping lines"
    )
    line_width: float = Field(
        default=2.0,
        ge=0,
        le=16.0,
        multiple_of=0.1,
        description="Half-width of each line in pixels (Gaussian core width)",
    )
    speed: float = Field(
        default=200.0,
        ge=0.0,
        le=255.0,
        multiple_of=1.0,
        description="Sweep speed in px/s at output resolution",
    )
    glow: float = Field(
        default=8.0,
        ge=0.0,
        le=16.0,
        multiple_of=1.0,
        description="Glow spread; Gaussian sigma in pixels",
    )
    origin: Literal["topLeft", "topRight", "bottomLeft", "bottomRight"] = Field(
        default="topLeft", description="Corner the lines emanate from"
    )
    seed: int | None = Field(
        default=None, description="Random seed for line offsets; None derives from clip id"
    )

    # Geometry precomputed in prepare()
    _skew_px: float = PrivateAttr(default=0.0)
    _period: float = PrivateAttr(default=0.0)
    _spacing: float = PrivateAttr(default=0.0)
    _half_len: float = PrivateAttr(default=0.0)
    _dx: float = PrivateAttr(default=0.0)
    _dy: float = PrivateAttr(default=0.0)
    _nx: float = PrivateAttr(default=0.0)
    _ny: float = PrivateAttr(default=0.0)
    _canvas_w: float = PrivateAttr(default=0.0)
    _canvas_h: float = PrivateAttr(default=0.0)
    _bounds_x: float = PrivateAttr(default=0.0)
    _bounds_y: float = PrivateAttr(default=0.0)
    _band_center_y: float = PrivateAttr(default=0.0)
    _line_base_ys: list[float] = PrivateAttr(default_factory=list)

    # GL objects — created lazily on first draw()
    _program: moderngl.Program | None = PrivateAttr(default=None)
    _vao: moderngl.VertexArray | None = PrivateAttr(default=None)

    async def prepare(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        b = bounds or Rect(0, 0, ctx.job.width, ctx.job.height)
        w, h = float(b.width), float(b.height)
        self._canvas_w = w
        self._canvas_h = float(ctx.job.height)
        self._bounds_x = float(b.x)
        self._bounds_y = float(b.y)

        # Negate so +angle matches progress-bar / tilt convention (CW, up left→right).
        skew = band_skew_px(w, -self.angle)
        is_bottom = self.origin in ("bottomLeft", "bottomRight")
        offset = (1.0 - self.offset_y) if is_bottom else self.offset_y
        center_y = band_left_center_y(h, offset, skew)
        half_h = (self.band_height / 2) * h

        skew_px = (center_y - half_h) - (center_y - half_h - skew)
        self._skew_px = skew_px

        diag = math.sqrt(w * w + skew_px * skew_px)
        dx = w / diag
        dy = -skew_px / diag
        self._dx = dx
        self._dy = dy
        self._nx = -dy
        self._ny = dx

        half_len = diag / 2
        self._half_len = half_len
        self._period = w + 2 * half_len
        self._spacing = self._period / self.line_count

        top_y = center_y - half_h
        self._band_center_y = center_y
        band_px_h = half_h * 2
        rng = (
            SeededRandom(self.seed) if self.seed is not None else SeededRandom.from_string(self.id)
        )
        self._line_base_ys = [top_y + rng.next() * band_px_h for _ in range(self.line_count)]

    def _set_uniform(self, prog: moderngl.Program, name: str, value: Any) -> None:
        """Helper to set uniforms while satisfying strict type checkers."""
        # We tell Pylance to safely assume this is a Uniform
        cast(moderngl.Uniform, prog[name]).value = value

    def draw(self, ctx: RenderContext) -> None:
        gl: moderngl.Context = ctx.canvas

        # Build GL objects once
        if self._program is None:
            self._program = gl.program(vertex_shader=_VERT, fragment_shader=_FRAG)
            vbo = gl.buffer(_QUAD.tobytes())
            self._vao = gl.simple_vertex_array(self._program, vbo, "in_vert")

        prog = self._program

        self._set_uniform(prog, "u_res", (self._canvas_w, float(ctx.bounds.height)))
        self._set_uniform(prog, "u_origin", (self._bounds_x, self._bounds_y))
        self._set_uniform(prog, "u_canvas_h", self._canvas_h)
        self._set_uniform(prog, "u_t", ctx.time.t)
        r, g, b, _ = resolve_color(self.color, ctx.job.colors).rgba
        self._set_uniform(prog, "u_color", (r, g, b))
        self._set_uniform(prog, "u_band_center_y", self._band_center_y)
        self._set_uniform(prog, "u_band_h", self.band_height)
        self._set_uniform(prog, "u_count", self.line_count)
        self._set_uniform(prog, "u_line_w", self.line_width)
        self._set_uniform(prog, "u_speed", ctx.job.scale_output_px(self.speed))
        self._set_uniform(prog, "u_opacity", self.opacity)
        self._set_uniform(prog, "u_glow", self.glow)
        self._set_uniform(prog, "u_skew_px", self._skew_px)
        self._set_uniform(prog, "u_period", self._period)
        self._set_uniform(prog, "u_spacing", self._spacing)
        self._set_uniform(prog, "u_half_len", self._half_len)
        self._set_uniform(prog, "u_dx", self._dx)
        self._set_uniform(prog, "u_dy", self._dy)
        self._set_uniform(prog, "u_right", 1 if self.origin in ("topRight", "bottomRight") else 0)

        padded = self._line_base_ys + [0.0] * (50 - len(self._line_base_ys))
        self._set_uniform(prog, "u_base_ys", tuple(padded))

        # Scissor clips rendering to the assigned bounds rect.
        # GL origin is bottom-left, so flip Y relative to full canvas height.
        bnd = ctx.bounds
        gl.scissor = (
            int(self._bounds_x),
            int(ctx.job.height - self._bounds_y - bnd.height),
            int(self._canvas_w),
            int(bnd.height),
        )

        assert self._vao is not None
        self._vao.render(moderngl.TRIANGLES)

        gl.scissor = None
