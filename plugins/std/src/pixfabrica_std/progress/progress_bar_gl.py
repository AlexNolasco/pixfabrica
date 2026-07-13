from __future__ import annotations

from typing import Any, ClassVar

import moderngl
import numpy as np
from pydantic import Field, PrivateAttr

from pixfabrica_core.clips import ClipCategory, ClipGL, ClipTag, PrepareContext, RenderContext
from pixfabrica_core.graphics import Rect
from pixfabrica_core.theme.color import Color, ColorToken, color_field, resolve_color
from pixfabrica_std.progress._progress_common import (
    TimeMode,
    TrackAnchor,
    playback_times,
    track_layout,
)
from pixfabrica_std.tilt import (
    ANGLE_BAND_DESC,
    ANGLE_BAND_SKEW_MAX,
    ANGLE_BAND_SKEW_MIN,
    band_skew_px,
)

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
uniform float u_progress;

uniform vec3  u_color;
uniform vec3  u_glow_color;
uniform float u_glow;
uniform float u_opacity;
uniform float u_offset_y;
uniform float u_skew_px;
uniform float u_half_h;

out vec4 frag_color;

float cross2(vec2 a, vec2 b) { return a.x * b.y - a.y * b.x; }

float edge_dist(vec2 p, vec2 a, vec2 b) {
    vec2 e = b - a;
    vec2 w = p - a;
    vec2 proj = e * clamp(dot(w, e) / dot(e, e), 0.0, 1.0);
    return length(w - proj);
}

// Signed distance to the filled parallelogram (negative inside).
float sd_fill_parallelogram(vec2 p, float prog, float y0, float slope, float hh) {
    if (prog <= 1e-6) {
        return edge_dist(p, vec2(0.0, y0 - hh), vec2(0.0, y0 + hh));
    }

    float yR = y0 + slope * prog;
    // CCW in y-up: bottom-left -> bottom-right -> top-right -> top-left.
    vec2 D = vec2(0.0, y0 - hh);
    vec2 C = vec2(prog, yR - hh);
    vec2 B = vec2(prog, yR + hh);
    vec2 A = vec2(0.0, y0 + hh);

    float d_edge = min(
        min(edge_dist(p, D, C), edge_dist(p, C, B)),
        min(edge_dist(p, B, A), edge_dist(p, A, D))
    );

    float h0 = cross2(C - D, p - D);
    float h1 = cross2(B - C, p - C);
    float h2 = cross2(A - B, p - B);
    float h3 = cross2(D - A, p - A);
    float inside_min = min(min(h0, h1), min(h2, h3));
    return inside_min > 0.0 ? -d_edge : d_edge;
}

void main() {
    float px = gl_FragCoord.x - u_origin.x;
    float py = (u_canvas_h - gl_FragCoord.y) - u_origin.y;

    float progress_px = u_progress * u_res.x;
    float glow_reach  = u_glow > 0.0 ? u_glow * 3.0 : 0.0;
    float slope       = abs(u_res.x) > 1e-6 ? u_skew_px / u_res.x : 0.0;
    float y0          = u_offset_y * u_res.y;

    vec2 p = vec2(px, py);
    float sd = sd_fill_parallelogram(p, progress_px, y0, slope, u_half_h);

    if (sd > glow_reach) {
        frag_color = vec4(0.0);
        return;
    }

    float core = 1.0 - smoothstep(-0.5, 0.5, sd);

    float halo = 0.0;
    if (u_glow > 0.0) {
        float g = max(u_glow, 0.5);
        float surface_dist = max(sd, 0.0);
        halo = exp(-0.5 * pow(surface_dist / g, 2.0));
    }

    float energy = clamp(core + halo, 0.0, 1.0);
    float alpha  = energy * u_opacity;

    vec3 final_color = mix(u_glow_color, u_color, core);
    frag_color = vec4(final_color * alpha, alpha);
}
"""

_QUAD = np.array([-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0], dtype="f4")


class ProgressBarGL(ClipGL):
    """GPU progress bar that fills left-to-right based on job playback position.
    Skewed like SweepLines; glow is uniform along the entire filled bar."""

    clip_type: ClassVar[str] = "std-progress-bar-gl"
    clip_category: ClassVar[ClipCategory] = ClipCategory.PROGRESS
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED, ClipTag.GL, ClipTag.GLOW]

    time_mode: TimeMode = Field(
        default="clip",
        description="Clock source: clip window (start/duration) or full composition timeline",
    )
    color: ColorToken | Color = color_field(ColorToken.PRIMARY)
    glow_color: ColorToken | Color = color_field(ColorToken.ACCENT)
    glow: float = Field(
        default=2.0,
        ge=0.0,
        le=20.0,
        multiple_of=0.1,
        description="Glow spread as a multiplier of bar height",
    )

    offset_y: float = Field(
        default=0.9,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Bar vertical position as fraction of bounds height (0=top, 1=bottom)",
    )
    offset_x: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Horizontal anchor as fraction of bounds width (0=left, 1=right)",
    )
    anchor_x: TrackAnchor = Field(
        default="center",
        description="How bar width expands from offset_x: left/right grow one way, center both",
    )
    width: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Bar length as a fraction of clip bounds width",
    )
    height: float = Field(
        default=0.004,
        ge=0.001,
        le=1.0,
        multiple_of=0.001,
        description="Bar thickness as fraction of bounds height",
    )
    angle: float = Field(
        default=0.0,
        ge=ANGLE_BAND_SKEW_MIN,
        le=ANGLE_BAND_SKEW_MAX,
        multiple_of=1.0,
        description=ANGLE_BAND_DESC,
    )
    opacity: float = Field(
        default=1.0, ge=0.0, le=1.0, multiple_of=0.1, description="Overall layer opacity"
    )
    _glow_px: float = PrivateAttr(default=0.0)
    _canvas_h: float = PrivateAttr(default=0.0)

    _program: moderngl.Program | None = PrivateAttr(default=None)
    _vao: moderngl.VertexArray | None = PrivateAttr(default=None)

    def _track_layout(self, bounds: Rect) -> tuple[float, float, float, float] | None:
        return track_layout(
            bounds,
            offset_x=self.offset_x,
            width=self.width,
            anchor_x=self.anchor_x,
        )

    async def prepare(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        b = bounds or Rect(0, 0, ctx.job.width, ctx.job.height)
        self._canvas_h = float(ctx.job.height)
        self._glow_px = self.glow * self.height * float(b.height)

    def _set_uniform(self, prog: moderngl.Program, name: str, value: Any) -> None:
        if name in prog:
            member = prog[name]
            if isinstance(member, moderngl.Uniform):
                member.value = value

    def draw(self, ctx: RenderContext) -> None:
        layout = self._track_layout(ctx.bounds)
        if layout is None:
            return

        track_x, track_y, track_w, bounds_h = layout
        skew_px = band_skew_px(track_w, self.angle)
        half_h_px = (self.height / 2.0) * bounds_h

        gl: moderngl.Context = ctx.canvas

        if self._program is None:
            self._program = gl.program(vertex_shader=_VERT, fragment_shader=_FRAG)
            vbo = gl.buffer(_QUAD.tobytes())
            self._vao = gl.simple_vertex_array(self._program, vbo, "in_vert")

        prog = self._program
        _, _, progress = playback_times(
            time_t=ctx.time.t,
            start=self.start,
            duration=self.duration,
            job_duration=ctx.job.duration,
            time_mode=self.time_mode,
        )

        self._set_uniform(prog, "u_res", (track_w, bounds_h))
        self._set_uniform(prog, "u_origin", (track_x, track_y))
        self._set_uniform(prog, "u_canvas_h", self._canvas_h)
        self._set_uniform(prog, "u_progress", progress)

        r, g, b, _ = resolve_color(self.color, ctx.job.colors).rgba
        self._set_uniform(prog, "u_color", (r, g, b))
        gr, gg, gb, _ = resolve_color(self.glow_color, ctx.job.colors).rgba
        self._set_uniform(prog, "u_glow_color", (gr, gg, gb))
        self._set_uniform(prog, "u_glow", self._glow_px)
        self._set_uniform(prog, "u_opacity", self.opacity)
        self._set_uniform(prog, "u_offset_y", self.offset_y)
        self._set_uniform(prog, "u_skew_px", skew_px)
        self._set_uniform(prog, "u_half_h", half_h_px)

        bnd = ctx.bounds
        gl.scissor = (
            int(bnd.x),
            int(ctx.job.height - bnd.y - bnd.height),
            int(bnd.width),
            int(bnd.height),
        )

        assert self._vao is not None
        self._vao.render(moderngl.TRIANGLES)

        gl.scissor = None
