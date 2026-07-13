from __future__ import annotations

from typing import Any, ClassVar, Literal, cast

import moderngl
import numpy as np
import skia
from pydantic import Field, PrivateAttr

from pixfabrica_core.clips import ClipCategory, ClipGL, ClipTag, PrepareContext, RenderContext
from pixfabrica_core.graphics import Rect
from pixfabrica_core.theme.color import Color, ColorToken, color_field, resolve_color
from pixfabrica_core.theme.typography import FontRole, FontSpec
from pixfabrica_std.text.skia_font import make_typography_font
from pixfabrica_std.tilt import ANGLE_FULL_DESC, ANGLE_FULL_MAX, ANGLE_FULL_MIN

_VERT = """
#version 330 core
in vec2 in_vert;
void main() { gl_Position = vec4(in_vert, 0.0, 1.0); }
"""

_FRAG = """
#version 330 core

uniform sampler2D u_text;
uniform sampler2D u_glow;
uniform vec2  u_tex_pos;      // texture top-left in canvas (top-down px)
uniform vec2  u_tex_size;     // texture dimensions in pixels
uniform vec2  u_canvas_size;  // full canvas size
uniform vec2  u_anchor;       // rotation pivot in canvas (top-down px)
uniform float u_angle;      // degrees, clockwise
uniform float u_glow_intensity;
uniform float u_has_glow;
uniform float u_opacity;

out vec4 frag_color;

void main() {
    // gl_FragCoord origin is bottom-left; convert to top-down canvas coords.
    float px = gl_FragCoord.x;
    float py = u_canvas_size.y - gl_FragCoord.y;

    // Rotate sample point around anchor (inverse rotation to find texture UV).
    vec2 d = vec2(px, py) - u_anchor;
    float rad = -radians(u_angle);
    float c = cos(rad), s = sin(rad);
    vec2 rotated = u_anchor + vec2(d.x * c - d.y * s, d.x * s + d.y * c);

    vec2 uv = (rotated - u_tex_pos) / u_tex_size;
    if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) {
        frag_color = vec4(0.0);
        return;
    }

    vec4 text_col = texture(u_text, uv) * u_opacity;
    vec4 glow_col = u_has_glow > 0.5
        ? texture(u_glow, uv) * u_glow_intensity
        : vec4(0.0);

    frag_color = clamp(glow_col + text_col, 0.0, 1.0);
}
"""

_QUAD = np.array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1], dtype="f4")


class GlowText(ClipGL):
    """Text clip rendered via GL with an optional Skia-blurred glow layer."""

    clip_type: ClassVar[str] = "std-glow-text"
    clip_category: ClassVar[ClipCategory] = ClipCategory.TEXT
    clip_tags: ClassVar[list[str]] = [ClipTag.GLOW, ClipTag.GL]

    text: str = Field(description="Text content to render")
    typography_role: FontRole = Field(
        default="body_medium", description="Typography role from the job theme"
    )
    color: ColorToken | Color = color_field(ColorToken.NEUTRAL)
    glow_color: ColorToken | Color = color_field(ColorToken.ACCENT)
    glow_radius: float = Field(
        default=20.0,
        ge=0.0,
        multiple_of=1.0,
        le=40.0,
        description="Blur radius of the glow halo in pixels",
    )
    offset_x: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Horizontal anchor as fraction of bounds width (0=left, 1=right)",
    )
    offset_y: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Vertical anchor as fraction of bounds height (0=top, 1=bottom)",
    )
    angle: float = Field(
        default=0.0,
        ge=ANGLE_FULL_MIN,
        le=ANGLE_FULL_MAX,
        multiple_of=1.0,
        description=ANGLE_FULL_DESC,
    )
    opacity: float = Field(default=1.0, ge=0.0, le=1.0, description="Overall layer opacity")
    align: Literal["left", "center", "right"] = Field(
        default="center", description="Text alignment relative to the offset_x anchor"
    )
    glow_intensity: float = Field(
        default=1.5,
        ge=0.0,
        multiple_of=0.1,
        le=3.0,
        description="Multiplier applied to the glow layer",
    )

    # Rasterized in prepare()
    _pixels: np.ndarray | None = PrivateAttr(default=None)
    _glow_pixels: np.ndarray | None = PrivateAttr(default=None)
    _tex_w: int = PrivateAttr(default=0)
    _tex_h: int = PrivateAttr(default=0)
    _tex_canvas_x: float = PrivateAttr(default=0.0)
    _tex_canvas_y: float = PrivateAttr(default=0.0)
    _anchor_x: float = PrivateAttr(default=0.0)
    _anchor_y: float = PrivateAttr(default=0.0)
    _canvas_w: float = PrivateAttr(default=0.0)
    _canvas_h: float = PrivateAttr(default=0.0)

    # GL objects — created lazily on first draw()
    _program: moderngl.Program | None = PrivateAttr(default=None)
    _vao: moderngl.VertexArray | None = PrivateAttr(default=None)
    _tex_text: moderngl.Texture | None = PrivateAttr(default=None)
    _tex_glow: moderngl.Texture | None = PrivateAttr(default=None)

    async def prepare(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        b = bounds or Rect(0, 0, ctx.job.width, ctx.job.height)
        self._canvas_w = float(ctx.job.width)
        self._canvas_h = float(ctx.job.height)

        spec: FontSpec = getattr(ctx.job.typography, self.typography_role)
        font = make_typography_font(spec)

        metrics = font.getMetrics()
        text_width = font.measureText(self.text)

        # Padding accommodates glow spread; min 2px to avoid clipping antialiasing.
        padding = int(self.glow_radius * 2) + 4 if self.glow_radius > 0 else 2
        self._tex_w = int(text_width) + 2 * padding
        self._tex_h = int(-metrics.fAscent + metrics.fDescent) + 2 * padding

        # Position of baseline within the texture (fAscent is negative).
        draw_x = float(padding)
        draw_y = float(padding) - metrics.fAscent

        # Canvas anchor for offset_x/y and rotation pivot
        x_anchor = b.x + self.offset_x * b.width
        y_anchor = b.y + self.offset_y * b.height
        self._anchor_x = x_anchor
        self._anchor_y = y_anchor

        # Baseline: shift so the visual center of the glyph box sits on y_anchor.
        baseline = y_anchor - (metrics.fAscent + metrics.fDescent) / 2.0

        match self.align:
            case "left":
                tex_x = x_anchor - padding
            case "right":
                tex_x = x_anchor - text_width - padding
            case _:
                tex_x = x_anchor - text_width / 2.0 - padding

        self._tex_canvas_x = tex_x
        # Top of texture = top of glyph box - padding
        self._tex_canvas_y = baseline + metrics.fAscent - padding

        self._pixels = self._rasterize(
            font, draw_x, draw_y, resolve_color(self.color, ctx.job.colors), sigma=0.0
        )

        if self.glow_radius > 0:
            sigma = max(self.glow_radius / 2.0, 0.5)
            self._glow_pixels = self._rasterize(
                font, draw_x, draw_y, resolve_color(self.glow_color, ctx.job.colors), sigma=sigma
            )

    def _rasterize(
        self, font: skia.Font, x: float, y: float, color: Color, sigma: float
    ) -> np.ndarray:
        surface = skia.Surface(self._tex_w, self._tex_h)
        canvas = surface.getCanvas()
        canvas.clear(skia.ColorTRANSPARENT)
        r, g, b, a = color.rgba
        paint = skia.Paint(AntiAlias=True)
        paint.setColor4f(skia.Color4f(r, g, b, a))
        if sigma > 0.0:
            paint.setImageFilter(skia.ImageFilters.Blur(sigma, sigma))
        canvas.drawString(self.text, x, y, font, paint)
        image = surface.makeImageSnapshot()
        return (
            np.frombuffer(image.tobytes(), dtype=np.uint8)
            .reshape(self._tex_h, self._tex_w, 4)
            .copy()
        )

    def _set_uniform(self, prog: moderngl.Program, name: str, value: Any) -> None:
        cast(moderngl.Uniform, prog[name]).value = value

    def draw(self, ctx: RenderContext) -> None:
        gl: moderngl.Context = ctx.canvas

        if self._program is None:
            self._program = gl.program(vertex_shader=_VERT, fragment_shader=_FRAG)
            vbo = gl.buffer(_QUAD.tobytes())
            self._vao = gl.simple_vertex_array(self._program, vbo, "in_vert")
            assert self._pixels is not None
            self._tex_text = gl.texture((self._tex_w, self._tex_h), 4, self._pixels.tobytes())
            if self._glow_pixels is not None:
                self._tex_glow = gl.texture(
                    (self._tex_w, self._tex_h), 4, self._glow_pixels.tobytes()
                )

        prog = self._program
        assert self._vao is not None
        assert self._tex_text is not None

        self._tex_text.use(location=0)
        (self._tex_glow or self._tex_text).use(location=1)

        self._set_uniform(prog, "u_text", 0)
        self._set_uniform(prog, "u_glow", 1)
        self._set_uniform(prog, "u_tex_pos", (self._tex_canvas_x, self._tex_canvas_y))
        self._set_uniform(prog, "u_tex_size", (float(self._tex_w), float(self._tex_h)))
        self._set_uniform(prog, "u_canvas_size", (self._canvas_w, self._canvas_h))
        self._set_uniform(prog, "u_anchor", (self._anchor_x, self._anchor_y))
        self._set_uniform(prog, "u_angle", self.angle)
        self._set_uniform(prog, "u_glow_intensity", self.glow_intensity)
        self._set_uniform(prog, "u_has_glow", 1.0 if self._tex_glow is not None else 0.0)
        self._set_uniform(prog, "u_opacity", self.opacity)

        bnd = ctx.bounds
        gl.scissor = (
            int(bnd.x),
            int(ctx.job.height - bnd.y - bnd.height),
            int(bnd.width),
            int(bnd.height),
        )

        self._vao.render(moderngl.TRIANGLES)
        gl.scissor = None
