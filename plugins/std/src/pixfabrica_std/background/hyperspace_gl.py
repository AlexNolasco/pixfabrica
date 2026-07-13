"""Hyperspace star-streak tunnel — port of Shadertoy "Interstellar" by Hazel Quantock (CC0).

Original: https://www.shadertoy.com/view/MdXGW2
Theme warm/cool palette tints depth-separated streaks.
Linear noise scroll at steady speed; bus onsets surge scroll and streak brightness.
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

from pixfabrica_core.audio.bus import AudioBusFrame
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
from pixfabrica_std.particles.drifting_dust_gl import (
    precompute_dust_gust_envelope,
    precompute_dust_time_warp,
)

log = logging.getLogger("pixfabrica.std.hyperspace_gl")

# Bump when fragment shader changes so cached GL programs recompile.
_SHADER_REVISION = 3

# ── Ray march / streak tuning ────────────────────────────────────────────────
_MARCH_STEPS = 15
_DRIFT_RATE = 1.0
_DEPTH_SCALE = 50.0
_CELL_SHARPNESS = 10.0
_STREAK_WIDTH = 2.2
_STREAK_GAIN = 1.2
_BURST_MIX = 0.75
_CORE_BLEND = 0.5
_GAMMA = 2.2

# ── Onset gust (baked; Heavy Warp preset raises speed instead) ───────────────
_GUST_BOOST = 4.5
_GUST_DURATION = 0.35
_GUST_SENSITIVITY = 0.0

# ── Depth noise texture (256×256 sparse star placement table) ────────────────
_DEFAULT_TEXTURE_NAME = "hyperspace_depth_noise.png"
_NOISE_SIZE = 256
_STAR_SPARSE_FRACTION = 0.22
_NOISE_SEED = 0x485350
_ALLOWED_EXT = frozenset({".png", ".jpg", ".jpeg", ".webp"})
_MAX_BYTES = MEDIA_UPLOAD_LIMITS["image"]
_MIN_DIM = 128
_MAX_DIM = 2048
_MIN_ASPECT = 0.25
_MAX_ASPECT = 4.0

_VERT = """
#version 330 core
in vec2 in_vert;
void main() { gl_Position = vec4(in_vert, 0.0, 1.0); }
"""

_FRAG = f"""
#version 330 core

#define MARCH_STEPS {_MARCH_STEPS}
#define GAMMA {_GAMMA}

uniform vec2  u_res;
uniform vec2  u_origin;
uniform float u_canvas_h;
uniform float u_scroll;
uniform float u_gust;
uniform float u_brightness;
uniform vec3  u_color_warm;
uniform vec3  u_color_cool;
uniform float u_luma_alpha;
uniform float u_opacity;
uniform vec2  u_noise_dim;
uniform sampler2D u_noise;

out vec4 frag_color;

vec3 ToGamma(vec3 col) {{
    return pow(max(col, vec3(0.0)), vec3(1.0 / GAMMA));
}}

float sampleNoise(vec2 pos) {{
    ivec2 cell = ivec2(pos);
    vec2 uv = (vec2(cell) + 0.5) / u_noise_dim;
    return texture(u_noise, uv).x;
}}

void main() {{
    float px = gl_FragCoord.x - u_origin.x;
    float py = (u_canvas_h - gl_FragCoord.y) - u_origin.y;
    if (px < 0.0 || px >= u_res.x || py < 0.0 || py >= u_res.y) discard;

    vec3 ray;
    ray.xy = 2.0 * (vec2(px, py) - u_res * 0.5) / u_res.x;
    ray.z = 1.0;

    float offset = u_scroll * {_DRIFT_RATE};
    float burst = 1.0 + (u_gust - 1.0) * {_BURST_MIX};
    float sw = {_STREAK_WIDTH};

    vec3 col = vec3(0.0);
    vec3 stp = ray / max(abs(ray.x), abs(ray.y));
    vec3 pos = 2.0 * stp + 0.5;

    for (int i = 0; i < MARCH_STEPS; i++) {{
        float z = sampleNoise(pos.xy);
        z = fract(z - offset);
        float d = {_DEPTH_SCALE} * z - pos.z;
        float w = pow(max(0.0, 1.0 - {_CELL_SHARPNESS} * length(fract(pos.xy) - 0.5)), 2.0);

        float lead  = max(0.0, 1.0 - abs(d + sw * 0.5) / sw);
        float core  = max(0.0, 1.0 - abs(d) / sw);
        float trail = max(0.0, 1.0 - abs(d - sw * 0.5) / sw);
        vec3 core_mix = mix(u_color_cool, u_color_warm, {_CORE_BLEND});
        vec3 streak = u_color_cool * lead + core_mix * core + u_color_warm * trail;

        col += {_STREAK_GAIN} * burst * (1.0 - z) * streak * w;
        pos += stp;
    }}

    col *= u_brightness;
    col = ToGamma(col);

    float luma  = dot(col, vec3(0.299, 0.587, 0.114));
    float alpha = mix(1.0, clamp(luma, 0.0, 1.0), u_luma_alpha) * u_opacity;
    frag_color  = vec4(col * alpha, alpha);
}}
"""

_QUAD = np.array(
    [-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0],
    dtype="f4",
)


def _procedural_depth_noise_rgb(size: int = _NOISE_SIZE) -> np.ndarray:
    """Sparse 256×256 depth table when the bundled PNG is unavailable."""
    rng = np.random.default_rng(_NOISE_SEED)
    depth = np.full((size, size), 0.88, dtype=np.float32)
    star_mask = rng.random((size, size)) < _STAR_SPARSE_FRACTION
    depth[star_mask] = rng.random(int(star_mask.sum())).astype(np.float32) * 0.42
    void = ~star_mask
    depth[void] = 0.72 + rng.random(int(void.sum())).astype(np.float32) * 0.26
    rgb = np.stack([depth, depth, depth * 0.97], axis=-1)
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
        log.warning("HyperspaceGL %s: could not resolve source %r — %s", clip_id, source, exc)
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
        log.warning("HyperspaceGL %s: failed to load image %r — %s", clip_id, local_path, exc)
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
        log.debug("HyperspaceGL: bundled default unavailable (%s) — using procedural noise", exc)
    return _procedural_depth_noise_rgb()


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


def _precompute_scroll_and_gust(
    *,
    total_frames: int,
    fps: float,
    speed: float,
    bus_select: str | None,
    bus_frames: list[AudioBusFrame] | None,
) -> tuple[np.ndarray, np.ndarray]:
    if total_frames <= 0:
        empty = np.zeros(0, dtype=np.float32)
        return empty, empty

    bus_connected = bool((bus_select or "").strip())
    if bus_connected and bus_frames:
        gust = precompute_dust_gust_envelope(
            total_frames=total_frames,
            fps=fps,
            clip_id="hyperspace",
            seed=None,
            sensitivity=_GUST_SENSITIVITY,
            gust_duration=_GUST_DURATION,
            gust_boost=_GUST_BOOST,
            bus_select=bus_select,
            bus_frames=bus_frames,
        )
    else:
        gust = np.ones(total_frames, dtype=np.float32)

    scroll = precompute_dust_time_warp(
        gust,
        fps=fps,
        speed=float(speed),
    )
    return scroll, gust


class HyperspaceGL(AudioVisualMixin, ClipGL):
    """Layered star streaks rush through a noise-driven tunnel — cool lead, warm trail.
    Bus onsets briefly accelerate drift; optional depth noise map."""

    clip_type: ClassVar[str] = "std-hyperspace-gl"
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
            id="heavy_warp",
            label="Heavy Warp",
            values={
                "speed": 1.8,
                "brightness": 1.15,
            },
        ),
        ClipPreset(
            id="slow_drift",
            label="Slow Drift",
            values={
                "speed": 0.5,
            },
        ),
        ClipPreset(
            id="sunset_warp",
            label="Sunset Warp",
            values={
                "color_warm": ColorToken.SECONDARY,
                "color_cool": ColorToken.PRIMARY,
            },
        ),
    ]

    source: str | None = Field(
        default=None,
        description="Optional star depth noise map (local path or http(s) URL); default is a sparse 256×256 table",
    )
    color_warm: ColorToken | Color = color_field(ColorToken.PRIMARY)
    color_cool: ColorToken | Color = color_field(ColorToken.SECONDARY)
    speed: float = Field(
        default=1.0,
        ge=0.1,
        le=3.0,
        multiple_of=0.1,
        description="Base star drift speed multiplier",
    )
    brightness: float = Field(
        default=1.0,
        ge=0.25,
        le=2.0,
        multiple_of=0.05,
        description="Overall streak brightness multiplier",
    )
    luma_alpha: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Luma-based transparency (0 = opaque black void, 1 = dark areas transparent)",
    )
    opacity: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Overall layer opacity",
    )

    _surface_rgb: np.ndarray | None = PrivateAttr(default=None)
    _noise_dim: tuple[float, float] = PrivateAttr(default=(256.0, 256.0))
    _scroll: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype=np.float32))
    _gust_envelope: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype=np.float32))
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

        total = max(ctx.job.total_frames, 0)
        self._scroll, self._gust_envelope = _precompute_scroll_and_gust(
            total_frames=total,
            fps=float(ctx.job.fps),
            speed=float(self.speed),
            bus_select=self.bus_select,
            bus_frames=self.bus_timeline(ctx),
        )
        self._surface_rgb = _resolve_surface_rgb(
            source=self.source,
            ctx=ctx,
            clip_id=self.id,
            clip_type=self.clip_type,
        )
        if self._surface_rgb is not None:
            h, w, _ = self._surface_rgb.shape
            self._noise_dim = (float(w), float(h))
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

    def _ensure_texture(self, gl: moderngl.Context) -> None:
        if self._tex is not None or self._surface_rgb is None:
            return
        h, w, _ = self._surface_rgb.shape
        self._tex = gl.texture((w, h), 3, self._surface_rgb.tobytes())
        self._tex.filter = (moderngl.NEAREST, moderngl.NEAREST)
        self._tex.repeat_x = True
        self._tex.repeat_y = True

    def _set_uniform(self, prog: moderngl.Program, name: str, value: Any) -> None:
        cast(moderngl.Uniform, prog[name]).value = value

    def _scroll_and_gust_for_frame(self, ctx: RenderContext) -> tuple[float, float]:
        if self._scroll.size > 0:
            f = max(0, min(ctx.time.frame, self._scroll.shape[0] - 1))
            return float(self._scroll[f]), float(self._gust_envelope[f])
        t = float(ctx.time.t) * float(self.speed)
        return t, 1.0

    def draw(self, ctx: RenderContext) -> None:
        gl: moderngl.Context = ctx.canvas

        self._ensure_program(gl)
        self._ensure_texture(gl)
        if self._tex is None:
            return

        prog = self._program
        assert prog is not None
        wr, wg, wb, _ = resolve_color(self.color_warm, ctx.job.colors).rgba
        cr, cg, cb, _ = resolve_color(self.color_cool, ctx.job.colors).rgba

        scroll, gust = self._scroll_and_gust_for_frame(ctx)

        self._set_uniform(prog, "u_res", (self._bounds_w, self._bounds_h))
        self._set_uniform(prog, "u_origin", (self._bounds_x, self._bounds_y))
        self._set_uniform(prog, "u_canvas_h", self._canvas_h)
        self._set_uniform(prog, "u_scroll", scroll)
        self._set_uniform(prog, "u_gust", gust)
        self._set_uniform(prog, "u_brightness", float(self.brightness))
        self._set_uniform(prog, "u_color_warm", (wr, wg, wb))
        self._set_uniform(prog, "u_color_cool", (cr, cg, cb))
        self._set_uniform(prog, "u_luma_alpha", float(self.luma_alpha))
        self._set_uniform(prog, "u_opacity", float(self.opacity))
        self._set_uniform(prog, "u_noise_dim", self._noise_dim)

        self._tex.use(0)
        self._set_uniform(prog, "u_noise", 0)

        gl.scissor = (
            int(self._bounds_x),
            int(ctx.job.height - self._bounds_y - ctx.bounds.height),
            int(self._bounds_w),
            int(self._bounds_h),
        )

        assert self._vao is not None
        self._vao.render(moderngl.TRIANGLES)

        gl.scissor = None
