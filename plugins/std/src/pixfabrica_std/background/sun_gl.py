"""Procedural sun with turbulent corona — port of Shadertoy lsf3RH by trisomie21.

Original: https://www.shadertoy.com/view/lsf3RH
Audio-driven brightness scales disc radius, corona turbulence, and surface warp.
Optional surface texture (iChannel0); bundled neutral granulation map otherwise.
"""

from __future__ import annotations

import asyncio
import logging
from importlib.resources import as_file, files
from pathlib import Path
from typing import Any, ClassVar, cast

import moderngl
import numpy as np
from PIL import Image as PILImage
from pydantic import Field, PrivateAttr

from pixfabrica_core.audio.bus import N_SPECTRUM, AudioBusFrame
from pixfabrica_core.audio.mixin import AudioVisualMixin
from pixfabrica_core.clips import (
    ClipCategory,
    ClipGL,
    ClipPreset,
    ClipTag,
    PrepareContext,
    RenderContext,
)
from pixfabrica_core.graphics import Rect
from pixfabrica_core.media_upload import MEDIA_UPLOAD_LIMITS
from pixfabrica_core.prepare_diagnostics import record_prepare_asset_failure
from pixfabrica_core.theme.color import Color, ColorToken, color_field, resolve_color
from pixfabrica_std.media_source import resolve_source_sync

log = logging.getLogger("pixfabrica.std.sun_gl")

# Bump when fragment shader changes so cached GL programs recompile.
_SHADER_REVISION = 5

_DEFAULT_TEXTURE_NAME = "sun_surface_default.png"
_ALLOWED_EXT = frozenset({".png", ".jpg", ".jpeg", ".webp"})
_MAX_BYTES = MEDIA_UPLOAD_LIMITS["image"]
_MIN_DIM = 128
_MAX_DIM = 2048
_MIN_ASPECT = 0.25
_MAX_ASPECT = 4.0
_SPEC_BIN_A = 4
_SPEC_BIN_B = 10

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
uniform float u_speed;
uniform float u_brightness;
uniform float u_scale;
uniform vec2  u_offset;
uniform vec3  u_color_body;
uniform vec3  u_color_glow;
uniform float u_luma_alpha;
uniform float u_opacity;
uniform sampler2D u_surface;

out vec4 frag_color;

float snoise(vec3 uv, float res) {
    const vec3 s = vec3(1e0, 1e2, 1e4);

    uv *= res;

    vec3 uv0 = floor(mod(uv, res)) * s;
    vec3 uv1 = floor(mod(uv + vec3(1.0), res)) * s;

    vec3 f = fract(uv);
    f = f * f * (3.0 - 2.0 * f);

    vec4 v = vec4(
        uv0.x + uv0.y + uv0.z, uv1.x + uv0.y + uv0.z,
        uv0.x + uv1.y + uv0.z, uv1.x + uv1.y + uv0.z
    );

    vec4 r = fract(sin(v * 1e-3) * 1e5);
    float r0 = mix(mix(r.x, r.y, f.x), mix(r.z, r.w, f.x), f.y);

    r = fract(sin((v + uv1.z - uv0.z) * 1e-3) * 1e5);
    float r1 = mix(mix(r.x, r.y, f.x), mix(r.z, r.w, f.x), f.y);

    return mix(r0, r1, f.z) * 2.0 - 1.0;
}

void main() {
    float px = gl_FragCoord.x - u_origin.x;
    float py = (u_canvas_h - gl_FragCoord.y) - u_origin.y;
    if (px < 0.0 || px >= u_res.x || py < 0.0 || py >= u_res.y) discard;

    float brightness = u_brightness;
    float radius     = 0.24 + brightness * 0.2;
    float invRadius  = 1.0 / radius;

    float time  = u_t * u_speed * 0.1;
    float aspect = u_res.x / u_res.y;
    vec2 uv = vec2(px, py) / u_res;

    vec2 p = uv - u_offset;
    p.x *= aspect;
    p /= max(u_scale, 0.01);

    float fade  = pow(length(2.0 * p), 0.5);
    float fVal1 = 1.0 - fade;
    float fVal2 = 1.0 - fade;

    float angle = atan(p.x, p.y) / 6.2832;
    float dist  = length(p);
    vec3 coord  = vec3(angle, dist, time * 0.1);

    float newTime1 = abs(snoise(
        coord + vec3(0.0, -time * (0.35 + brightness * 0.001), time * 0.015), 15.0));
    float newTime2 = abs(snoise(
        coord + vec3(0.0, -time * (0.15 + brightness * 0.001), time * 0.015), 45.0));

    for (int i = 1; i <= 7; i++) {
        float power = pow(2.0, float(i + 1));
        fVal1 += (0.5 / power) * snoise(
            coord + vec3(0.0, -time, time * 0.2),
            power * 10.0 * (newTime1 + 1.0));
        fVal2 += (0.5 / power) * snoise(
            coord + vec3(0.0, -time, time * 0.2),
            power * 25.0 * (newTime2 + 1.0));
    }

    float corona  = pow(fVal1 * max(1.1 - fade, 0.0), 2.0) * 50.0;
    corona       += pow(fVal2 * max(1.1 - fade, 0.0), 2.0) * 50.0;
    corona       *= 1.2 - newTime1;

    // Stereographic disc — only inside the sun. Never evaluate globally: the original
    // added f at every pixel; with sp = -1 + 2*(uv-offset) that puts a second sun at
    // offset + 0.5 (lower-right corner at default anchor).
    vec3 discBody = vec3(0.0);
    vec3 starSphere = vec3(0.0);
    if (dist < radius) {
        corona *= pow(dist * invRadius, 24.0);

        vec2 sp = 2.0 * (uv - u_offset);
        sp.x *= aspect;
        sp *= (2.0 - brightness);
        float sr = dot(sp, sp);
        float f = (1.0 - sqrt(abs(1.0 - sr))) / max(sr, 1e-6) + brightness * 0.5;

        discBody = vec3(f * (0.75 + brightness * 0.3));
        vec2 newUv = vec2(sp.x * f, sp.y * f) + vec2(time, 0.0);

        vec3 texSample = texture(u_surface, newUv).rgb;
        float uOff = texSample.g * brightness * 4.5 + time;
        starSphere = texture(u_surface, newUv + vec2(uOff, 0.0)).rgb;
    }

    // Hard mask: stereographic f peaks at uv = offset + 0.5 (lower-right at default
    // anchor) when evaluated globally. Zero disc texture outside the sun radius.
    float insideDisc = step(dist, radius);
    discBody *= insideDisc;
    starSphere *= insideDisc;

    float starGlow = min(max(1.0 - dist * (1.0 - brightness), 0.0), 1.0);
    starGlow *= 1.0 - smoothstep(radius * 0.85, radius * 2.2, dist);

    vec3 col = discBody * u_color_body
             + starSphere * u_color_body
             + corona * u_color_body
             + starGlow * u_color_glow;

    float luma  = dot(col, vec3(0.299, 0.587, 0.114));
    float alpha = mix(1.0, clamp(luma, 0.0, 1.0), u_luma_alpha) * u_opacity;
    frag_color  = vec4(col * alpha, alpha);
}
"""

_QUAD = np.array(
    [-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0],
    dtype="f4",
)


def _frac(x: np.ndarray) -> np.ndarray:
    return x - np.floor(x)


def _procedural_surface_rgb(size: int = 512) -> np.ndarray:
    """Tile-friendly neutral granulation when the bundled PNG is unavailable."""
    ys, xs = np.mgrid[0:size, 0:size].astype(np.float32)
    p = np.stack([xs, ys], axis=-1)
    h = np.sin(p[..., 0] * 0.031 + p[..., 1] * 0.047) * 43758.5453
    h += np.sin(p[..., 0] * 0.011 + p[..., 1] * 0.019 + 12.9898) * 127.1
    h += np.sin(p[..., 0] * 0.073 + p[..., 1] * 0.091) * 53.13
    v = (_frac(np.sin(h) * 43758.5453) * 0.55 + 0.22).astype(np.float32)
    rgb = np.stack([v, v * 0.98, v * 0.94], axis=-1)
    return np.clip(rgb * 255.0, 0, 255).astype(np.uint8)


def _validate_source_path(path: Path) -> str | None:
    ext = path.suffix.lower()
    if ext not in _ALLOWED_EXT:
        return "unsupported_extension"
    try:
        size = path.stat().st_size
    except OSError:
        return "unreadable"
    if size <= 0 or size > _MAX_BYTES:
        return "file_size"
    return None


def _prepare_rgb_from_pil(pil_img: PILImage.Image) -> np.ndarray | None:
    w, h = pil_img.size
    if w < _MIN_DIM or h < _MIN_DIM:
        return None
    aspect = w / h if h else 0.0
    if aspect < _MIN_ASPECT or aspect > _MAX_ASPECT:
        return None
    if max(w, h) > _MAX_DIM:
        pil_img = pil_img.copy()
        pil_img.thumbnail((_MAX_DIM, _MAX_DIM), PILImage.Resampling.LANCZOS)
    return np.array(pil_img.convert("RGB"), dtype=np.uint8)


def _load_user_source_rgb(
    source: str, ctx: PrepareContext, clip_id: str, clip_type: str
) -> np.ndarray | None:
    try:
        local_path = resolve_source_sync(source, ctx)
    except Exception as exc:
        record_prepare_asset_failure(
            ctx,
            kind="clip",
            ref_id=clip_id,
            clip_type=clip_type,
            field="source",
            source=source,
            exc=exc,
        )
        log.warning("SunGL %s: could not resolve source %r — %s", clip_id, source, exc)
        return None

    reason = _validate_source_path(local_path)
    if reason:
        record_prepare_asset_failure(
            ctx,
            kind="clip",
            ref_id=clip_id,
            clip_type=clip_type,
            field="source",
            source=source,
            exc=ValueError(reason),
            code=reason,
        )
        return None

    try:
        pil_img = PILImage.open(str(local_path))
        rgb = _prepare_rgb_from_pil(pil_img)
    except Exception as exc:
        record_prepare_asset_failure(
            ctx,
            kind="clip",
            ref_id=clip_id,
            clip_type=clip_type,
            field="source",
            source=source,
            exc=exc,
            code="load_failed",
        )
        log.warning("SunGL %s: failed to load image %r — %s", clip_id, local_path, exc)
        return None

    if rgb is None:
        record_prepare_asset_failure(
            ctx,
            kind="clip",
            ref_id=clip_id,
            clip_type=clip_type,
            field="source",
            source=source,
            exc=ValueError("dimensions_or_aspect"),
            code="invalid_dimensions",
        )
    return rgb


def _load_bundled_rgb() -> np.ndarray:
    try:
        with as_file(
            files("pixfabrica_std") / "background" / "resources" / _DEFAULT_TEXTURE_NAME
        ) as path:
            pil_img = PILImage.open(path)
            rgb = _prepare_rgb_from_pil(pil_img)
            if rgb is not None:
                return rgb
    except Exception as exc:
        log.debug("SunGL: bundled default unavailable (%s) — using procedural noise", exc)
    return _procedural_surface_rgb()


def _resolve_surface_rgb(
    *,
    source: str | None,
    ctx: PrepareContext,
    clip_id: str,
    clip_type: str,
) -> np.ndarray:
    if source and source.strip():
        user_rgb = _load_user_source_rgb(source.strip(), ctx, clip_id, clip_type)
        if user_rgb is not None:
            return user_rgb
    return _load_bundled_rgb()


def _live_brightness_from_frame(spec: list[float]) -> float:
    if len(spec) < N_SPECTRUM:
        return 0.0
    return float(spec[_SPEC_BIN_A]) * 0.25 + float(spec[_SPEC_BIN_B]) * 0.25


def _precompute_brightness_history(
    frames: list[AudioBusFrame] | None,
    total: int,
    *,
    base_brightness: float,
    sensitivity: float,
) -> np.ndarray:
    history = np.full(max(total, 0), base_brightness, dtype=np.float32)
    if total <= 0 or not frames:
        return history
    n_bus = min(total, len(frames))
    base = float(base_brightness)
    sens = float(sensitivity)
    for f in range(total):
        if f < n_bus:
            live = _live_brightness_from_frame(frames[f].spectrum)
            history[f] = min(1.0, max(0.0, base + live * sens))
        else:
            history[f] = base
    return history


class SunGL(AudioVisualMixin, ClipGL):
    """Turbulent procedural sun with audio-reactive corona and disc detail.
    Optional surface texture; bus brightness drives radius, glow, and surface warp."""

    clip_type: ClassVar[str] = "std-sun-gl"
    clip_category: ClassVar[ClipCategory] = ClipCategory.BACKGROUND
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED, ClipTag.GL, ClipTag.AUDIO_REACTIVE]
    clip_presets: ClassVar[list[ClipPreset]] = [
        ClipPreset(
            id="classic",
            label="Classic",
            values={
                "luma_alpha": 0.0,
                "opacity": 1.0,
            },
        ),
        ClipPreset(
            id="overlay",
            label="Overlay",
            values={
                "luma_alpha": 1.0,
                "opacity": 1.0,
            },
        ),
        ClipPreset(
            id="sunrise",
            label="Sunrise",
            values={
                "offset_y": 0.85,
                "scale": 1.1,
            },
        ),
        ClipPreset(
            id="red_giant",
            label="Red Giant",
            values={
                "scale": 1.25,
                "base_brightness": 0.45,
            },
        ),
    ]

    source: str | None = Field(
        default=None,
        description="Optional sun surface / granulation map (local path or http(s) URL)",
    )
    color_body: ColorToken | Color = color_field(ColorToken.PRIMARY)
    color_glow: ColorToken | Color = color_field(ColorToken.SECONDARY)
    base_brightness: float = Field(
        default=0.35,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Calm sun level when no bus is active; floor when bus adds energy",
    )
    speed: float = Field(
        default=1.0,
        ge=0.1,
        le=3.0,
        multiple_of=0.1,
        description="Corona drift and surface scroll speed multiplier",
    )
    sensitivity: float = Field(
        default=1.0,
        ge=0.1,
        le=8.0,
        multiple_of=0.1,
        description="Audio response gain on live brightness after job-wide normalization",
    )
    scale: float = Field(
        default=1.0,
        ge=0.25,
        le=3.0,
        multiple_of=0.05,
        description="Sun size multiplier (disc and corona)",
    )
    offset_x: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Horizontal anchor within bounds (0.5 = centered)",
    )
    offset_y: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Vertical anchor within bounds (0 = top, 0.5 = center, 1 = bottom)",
    )
    luma_alpha: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Luma-based transparency (0 = opaque black sky, 1 = dark areas transparent)",
    )
    opacity: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Overall layer opacity",
    )

    _surface_rgb: np.ndarray | None = PrivateAttr(default=None)
    _brightness_history: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype="f4"))
    _canvas_h: float = PrivateAttr(default=0.0)
    _bounds_x: float = PrivateAttr(default=0.0)
    _bounds_y: float = PrivateAttr(default=0.0)
    _bounds_w: float = PrivateAttr(default=0.0)
    _bounds_h: float = PrivateAttr(default=0.0)
    _program: moderngl.Program | None = PrivateAttr(default=None)
    _vao: moderngl.VertexArray | None = PrivateAttr(default=None)
    _tex: moderngl.Texture | None = PrivateAttr(default=None)
    _shader_revision: int = PrivateAttr(default=0)

    async def prepare(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        await asyncio.to_thread(self._prepare_sync, ctx, bounds)

    def _prepare_sync(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        b = bounds or Rect(0, 0, ctx.job.width, ctx.job.height)
        self._canvas_h = float(ctx.job.height)
        self._bounds_x = float(b.x)
        self._bounds_y = float(b.y)
        self._bounds_w = float(b.width)
        self._bounds_h = float(b.height)

        bus = self.bus_timeline(ctx)
        total = max(ctx.job.total_frames, 0)
        self._brightness_history = _precompute_brightness_history(
            bus,
            total,
            base_brightness=float(self.base_brightness),
            sensitivity=float(self.sensitivity),
        )
        self._surface_rgb = _resolve_surface_rgb(
            source=self.source,
            ctx=ctx,
            clip_id=self.id,
            clip_type=self.clip_type,
        )
        self._tex = None
        self._program = None
        self._vao = None
        self._shader_revision = 0

    def _ensure_program(self, gl: moderngl.Context) -> None:
        if self._program is not None and self._shader_revision == _SHADER_REVISION:
            return
        self._program = gl.program(vertex_shader=_VERT, fragment_shader=_FRAG)
        vbo = gl.buffer(_QUAD.tobytes())
        self._vao = gl.simple_vertex_array(self._program, vbo, "in_vert")
        self._shader_revision = _SHADER_REVISION

    def _brightness_for_frame(self, ctx: RenderContext) -> float:
        base = float(self.base_brightness)
        if not self.bus_active_for_draw(ctx):
            return base
        if self._brightness_history.shape[0] > 0:
            f = max(0, min(ctx.time.frame, self._brightness_history.shape[0] - 1))
            return float(self._brightness_history[f])
        live = _live_brightness_from_frame(ctx.audio_bus_frame.spectrum)
        live = min(1.0, max(0.0, live * float(self.sensitivity)))
        return min(1.0, max(0.0, base + live))

    def _ensure_texture(self, gl: moderngl.Context) -> None:
        if self._tex is not None or self._surface_rgb is None:
            return
        h, w, _ = self._surface_rgb.shape
        self._tex = gl.texture((w, h), 3, self._surface_rgb.tobytes())
        self._tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self._tex.repeat_x = True
        self._tex.repeat_y = True

    def _set_uniform(self, prog: moderngl.Program, name: str, value: Any) -> None:
        cast(moderngl.Uniform, prog[name]).value = value

    def draw(self, ctx: RenderContext) -> None:
        gl: moderngl.Context = ctx.canvas

        self._ensure_program(gl)
        self._ensure_texture(gl)
        if self._tex is None:
            return

        prog = self._program
        assert prog is not None
        br, bg, bb, _ = resolve_color(self.color_body, ctx.job.colors).rgba
        gr, gg, gb, _ = resolve_color(self.color_glow, ctx.job.colors).rgba

        self._set_uniform(prog, "u_res", (self._bounds_w, self._bounds_h))
        self._set_uniform(prog, "u_origin", (self._bounds_x, self._bounds_y))
        self._set_uniform(prog, "u_canvas_h", self._canvas_h)
        self._set_uniform(prog, "u_t", float(ctx.time.t))
        self._set_uniform(prog, "u_speed", float(self.speed))
        self._set_uniform(prog, "u_brightness", self._brightness_for_frame(ctx))
        self._set_uniform(prog, "u_scale", float(self.scale))
        self._set_uniform(prog, "u_offset", (float(self.offset_x), float(self.offset_y)))
        self._set_uniform(prog, "u_color_body", (br, bg, bb))
        self._set_uniform(prog, "u_color_glow", (gr, gg, gb))
        self._set_uniform(prog, "u_luma_alpha", float(self.luma_alpha))
        self._set_uniform(prog, "u_opacity", float(self.opacity))

        self._tex.use(0)
        self._set_uniform(prog, "u_surface", 0)

        gl.scissor = (
            int(self._bounds_x),
            int(ctx.job.height - self._bounds_y - ctx.bounds.height),
            int(self._bounds_w),
            int(self._bounds_h),
        )

        assert self._vao is not None
        self._vao.render(moderngl.TRIANGLES)

        gl.scissor = None
