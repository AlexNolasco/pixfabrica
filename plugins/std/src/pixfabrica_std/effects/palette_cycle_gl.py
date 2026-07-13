"""Full-frame palette cycling post-process — hue-rotate theme swatches, HSV snap, luma preserve."""

from __future__ import annotations

import math
from typing import Any, ClassVar

import moderngl
import numpy as np
from pydantic import BaseModel, Field, PrivateAttr

from pixfabrica_core.audio.mixin import AudioVisualMixin
from pixfabrica_core.clips import (
    ClipCategory,
    ClipTag,
    GLPostProcessClip,
    PrepareContext,
    RenderContext,
)
from pixfabrica_core.graphics import Rect
from pixfabrica_core.theme.color import Color, ColorPalette, ColorToken, color_field, resolve_color
from pixfabrica_std.mesh.shader_helper import precompute_bus_drives

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
uniform vec3 u_palette[8];
uniform int u_palette_count;
uniform float u_cycle_phase;
uniform float u_intensity;

in vec2 v_uv;
out vec4 fragColor;

const float GRAY_SAT_THRESHOLD = 0.08;
const vec3 LUMA = vec3(0.299, 0.587, 0.114);

vec3 rgb2hsv(vec3 c) {
    vec4 K = vec4(0.0, -1.0 / 3.0, 2.0 / 3.0, -1.0);
    vec4 p = mix(vec4(c.bg, K.wz), vec4(c.gb, K.xy), step(c.b, c.g));
    vec4 q = mix(vec4(p.xyw, c.r), vec4(c.r, p.yzx), step(p.x, c.r));
    float d = q.x - min(q.w, q.y);
    float e = 1.0e-10;
    return vec3(abs(q.z + (q.w - q.y) / (6.0 * d + e)), d / (q.x + e), q.x);
}

vec3 hsv2rgb(vec3 c) {
    vec4 K = vec4(1.0, 2.0 / 3.0, 1.0 / 3.0, 3.0);
    vec3 p = abs(fract(c.xxx + K.xyz) * 6.0 - K.www);
    return c.z * mix(K.xxx, clamp(p - K.xxx, 0.0, 1.0), c.y);
}

float hue_dist(float a, float b) {
    float d = abs(a - b);
    return min(d, 1.0 - d);
}

void main() {
    vec4 src = texture(u_source, v_uv);
    vec3 original = src.rgb;
    vec3 px_hsv = rgb2hsv(original);

    if (px_hsv.y < GRAY_SAT_THRESHOLD) {
        fragColor = vec4(original, src.a);
        return;
    }

    float best_dist = 1e9;
    vec3 best_rgb = original;

    for (int i = 0; i < 8; i++) {
        if (i >= u_palette_count) {
            break;
        }
        vec3 swatch_hsv = rgb2hsv(u_palette[i]);
        swatch_hsv.x = fract(swatch_hsv.x + u_cycle_phase);
        vec3 rotated = hsv2rgb(swatch_hsv);
        vec3 match_hsv = rgb2hsv(rotated);
        float dist = hue_dist(px_hsv.x, match_hsv.x) + abs(px_hsv.y - match_hsv.y);
        if (dist < best_dist) {
            best_dist = dist;
            best_rgb = rotated;
        }
    }

    float orig_luma = dot(original, LUMA);
    float snap_luma = dot(best_rgb, LUMA);
    vec3 remapped = best_rgb * (orig_luma / max(snap_luma, 1.0e-5));
    vec3 out_rgb = mix(original, remapped, u_intensity);
    fragColor = vec4(out_rgb, src.a);
}
"""

_QUAD = np.array([-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0], dtype="f4")

CHROMATIC_TOKENS: tuple[ColorToken, ...] = (
    ColorToken.PRIMARY,
    ColorToken.SECONDARY,
    ColorToken.TERTIARY,
    ColorToken.ACCENT,
)
MAX_PALETTE = 8


class PaletteSwatch(BaseModel):
    """One row in a custom palette list (``color_list`` in gen-ui)."""

    color: ColorToken | Color = color_field(ColorToken.PRIMARY)


def resolve_palette_colors(
    custom_palette: list[PaletteSwatch],
    job_colors: ColorPalette,
) -> list[tuple[float, float, float]]:
    """Resolve RGB tuples for the shader palette uniform."""
    if custom_palette:
        colors = [
            resolve_color(swatch.color, job_colors) for swatch in custom_palette[:MAX_PALETTE]
        ]
    else:
        colors = [resolve_color(token, job_colors) for token in CHROMATIC_TOKENS]
    return [color.rgba[:3] for color in colors]


def pad_palette_uniform(
    palette: list[tuple[float, float, float]],
    *,
    size: int = MAX_PALETTE,
) -> list[tuple[float, float, float]]:
    """Pad palette to a fixed GLSL array length (moderngl rejects partial vec3[N])."""
    if len(palette) >= size:
        return palette[:size]
    pad = (0.0, 0.0, 0.0)
    return palette + [pad] * (size - len(palette))


def effective_blend_intensity(
    *,
    intensity: float,
    sensitivity: float,
    amplitude: float,
    bus_connected: bool,
) -> float:
    """Map knob + optional normalized bus amplitude (0–1) to the shader blend factor."""
    if not bus_connected:
        return float(intensity)
    amp = min(1.0, max(0.0, amplitude) * float(sensitivity))
    return float(intensity) * (0.5 + 0.5 * amp)


def cycle_phase(*, offset: float, time_s: float, speed: float) -> float:
    """Hue rotation phase in 0..1 (one full rotation)."""
    return math.fmod(float(offset) + float(time_s) * float(speed), 1.0)


class PaletteCycle(AudioVisualMixin, GLPostProcessClip):
    """Cycle chromatic theme colors across the composited frame with luma-preserved posterize.

    Stack before vignette/scanlines on a GLEffectTrack (``std-post-track``). Uses the four
    chromatic theme tokens by default; an optional custom palette replaces them entirely.
    """

    clip_type: ClassVar[str] = "std-palette-cycle"
    clip_category: ClassVar[ClipCategory] = ClipCategory.POSTPROCESS
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED, ClipTag.AUDIO_REACTIVE, ClipTag.GL]

    intensity: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        multiple_of=0.05,
        description="Maximum blend between original (0) and palette-snapped (1)",
    )
    sensitivity: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.05,
        description="How strongly bus amplitude pushes intensity (0 = half max, 1 = full max)",
    )
    speed: float = Field(
        default=0.25,
        ge=0.0,
        le=10.0,
        multiple_of=0.05,
        description="Hue rotations per second",
    )
    offset: float = Field(
        default=0.0,
        ge=0.0,
        lt=1.0,
        multiple_of=0.01,
        description="Cycle phase offset (0–1) for syncing color hits",
    )
    palette: list[PaletteSwatch] = Field(
        default_factory=list,
        max_length=MAX_PALETTE,
        description="Optional custom swatches; replaces theme chromatics when set",
    )

    _amp_history: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype=np.float32))
    _program: moderngl.Program | None = PrivateAttr(default=None)
    _vao: moderngl.VertexArray | None = PrivateAttr(default=None)

    async def prepare(self, ctx: PrepareContext, _bounds: Rect | None = None) -> None:
        total = max(ctx.job.total_frames, 0)
        _, _, _, self._amp_history = precompute_bus_drives(self.bus_timeline(ctx), total)

    def _amp_drive_for_frame(self, ctx: RenderContext) -> float:
        if not (self.bus_select or "").strip():
            return 0.0
        if self._amp_history.shape[0] > 0:
            f = max(0, min(ctx.time.frame, self._amp_history.shape[0] - 1))
            return min(1.0, float(self._amp_history[f]))
        return min(1.0, max(0.0, float(ctx.audio_bus_frame.amplitude)))

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

        palette = resolve_palette_colors(self.palette, ctx.job.colors)
        palette_uniform = pad_palette_uniform(palette)
        bus_connected = bool((self.bus_select or "").strip())
        blend = effective_blend_intensity(
            intensity=self.intensity,
            sensitivity=self.sensitivity,
            amplitude=self._amp_drive_for_frame(ctx),
            bus_connected=bus_connected,
        )
        phase = cycle_phase(offset=self.offset, time_s=ctx.time.t, speed=self.speed)

        prog = self._program
        ctx.source_texture.use(location=0)
        self._set_uniform(prog, "u_source", 0)
        self._set_uniform(prog, "u_palette", palette_uniform)
        self._set_uniform(prog, "u_palette_count", len(palette))
        self._set_uniform(prog, "u_cycle_phase", phase)
        self._set_uniform(prog, "u_intensity", blend)

        assert self._vao is not None
        self._vao.render(moderngl.TRIANGLES)
