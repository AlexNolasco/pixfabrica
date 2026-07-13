"""Raymarched music room — LED EQ on four walls, ceiling panels, and bass-reactive lighting.

Peak caps are precomputed in prepare() (parallel-safe; no GPU feedback buffer).
Adapted from a Shadertoy music-room style shader (CC0-style port).
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, ClassVar

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
from pixfabrica_core.file_upload_policy import JobBoundsFactorPolicy
from pixfabrica_core.graphics import Rect
from pixfabrica_core.media_upload import MEDIA_UPLOAD_LIMITS
from pixfabrica_core.prepare_diagnostics import record_prepare_asset_failure
from pixfabrica_core.theme.color import Color, ColorToken, color_field, resolve_color
from pixfabrica_core.ui_schema import (
    stock_attribution_field,
    stock_image_field,
    stock_provider_field,
)
from pixfabrica_std.common import FitMode
from pixfabrica_std.media_source import resolve_local_source_path, resolve_source_sync

log = logging.getLogger("pixfabrica.std.music_room_gl")

_SHADER_REVISION = 11

# ── Bar / peak tuning (module-level; not timeline knobs) ─────────────────────
_MAX_BARS = 32
_NUM_WALLS = 4
_SMOOTHING = 0.35
_PEAK_HOLD = 0.4
_PEAK_FALL = 0.6

# ── Motion bases (scaled by ``motion`` param) ────────────────────────────────
_ROT_SPEED_DEFAULT = 0.40
_BOB_AMT_BASE = 0.18
_BOB_SPEED_BASE = 0.25
_CAM_BOB_BASE = 0.08

# ── Image upload policy ──────────────────────────────────────────────────────
_ALLOWED_EXT = frozenset({".png", ".jpg", ".jpeg", ".webp"})
_MAX_BYTES = MEDIA_UPLOAD_LIMITS["image"]
_MIN_DIM = 128
_MAX_DIM = 2048
_MIN_ASPECT = 0.25
_MAX_ASPECT = 4.0

_DEFAULT_LAMP_HEX = "#5588FF"

# Cap long edge at factor × max(job width, job height) — same as std-background-image.
_TEXTURE_MAX_DIM_FACTOR = 1.5

# ── Shader baked constants ───────────────────────────────────────────────────
_NUM_LEDS = 12
_EQ_BOTTOM = 0.03
_EQ_TOP = 0.34
_EQ_BRIGHT = 4.2
_EQ_GLOW = 0.25
_EQ_GAP = 0.02
_CAM_H = 1.2
_CAM_PITCH = -0.05
_FOV = 0.85
_LAMP_INTENSITY = 1.1
_LAMP_BASS_PULSE = 0.6
_AMBIENT = 0.5
_PANEL_LONG = 5.5
_PANEL_SHORT = 0.80
_PANEL_BRIGHT = 1.4
_PANEL_EDGE = 0.05
_CONE_STEPS = 16
_CONE_STRENGTH = 0.16
_CONE_SPREAD = 0.30
_FLOOR_REFLECT = 0.05
_FLOOR_TILE = 0.06
_POOL_STRENGTH = 0.8
_FOG = 0.016
_VIGNETTE = 0.45
_EXPOSURE = 0.45
_FLOOR_TILE_SIZE = 2.4
_GROUT_WIDTH = 0.035
_WALL_COLOR = (0.0, 0.0, 0.0)
_EDGE_COLOR = (0.0, 0.0, 0.0)
_EDGE_WIDTH = 0.02
_EDGE_SOFT = 0.02
_WALL_VIVIDNESS_DEFAULT = 1.5

# --- ROOM MOTION ---
_ROOM_TILT = 0.12  # how far the room's spin axis leans off vertical (radians)
_TILT_WOBBLE = 0.04  # slow breathing of the tilt amount (0 = rigid wobble)
_TILT_SPEED = 0.18  # speed of that breathing

_VERT = """
#version 330 core
in vec2 in_vert;
void main() { gl_Position = vec4(in_vert, 0.0, 1.0); }
"""

_FRAG = f"""
#version 330 core

#define MAX_BARS   {_MAX_BARS}.0
#define NUM_LEDS   {_NUM_LEDS}.0
#define EQ_BOTTOM  {_EQ_BOTTOM}
#define EQ_TOP     {_EQ_TOP}
#define EQ_BRIGHT  {_EQ_BRIGHT}
#define EQ_GLOW    {_EQ_GLOW}
#define EQ_GAP     {_EQ_GAP}
#define CAM_H      {_CAM_H}
#define CAM_PITCH  {_CAM_PITCH}
#define ROOM_TILT  {_ROOM_TILT}
#define FOV        {_FOV}
#define LAMP_INTENSITY  {_LAMP_INTENSITY}
#define LAMP_BASS_PULSE {_LAMP_BASS_PULSE}
#define AMBIENT         {_AMBIENT}
#define PANEL_LONG   {_PANEL_LONG}
#define PANEL_SHORT  {_PANEL_SHORT}
#define PANEL_BRIGHT {_PANEL_BRIGHT}
#define PANEL_EDGE   {_PANEL_EDGE}
#define CONE_STEPS    {_CONE_STEPS}
#define CONE_STRENGTH {_CONE_STRENGTH}
#define CONE_SPREAD   {_CONE_SPREAD}
#define FLOOR_REFLECT {_FLOOR_REFLECT}
#define FLOOR_TILE    {_FLOOR_TILE}
#define POOL_STRENGTH {_POOL_STRENGTH}
#define FOG        {_FOG}
#define VIGNETTE   {_VIGNETTE}
#define EXPOSURE   {_EXPOSURE}
#define FLOOR_TILE_SIZE {_FLOOR_TILE_SIZE}
#define GROUT_WIDTH     {_GROUT_WIDTH}
#define EDGE_WIDTH  {_EDGE_WIDTH}
#define EDGE_SOFT   {_EDGE_SOFT}
#define TILT_WOBBLE {_TILT_WOBBLE}
#define TILT_SPEED   {_TILT_SPEED}

uniform vec2  u_res;
uniform vec2  u_origin;
uniform float u_canvas_h;
uniform float u_t;
uniform float u_room_w;
uniform float u_room_h;
uniform float u_rot_speed;
uniform float u_bob_amt;
uniform float u_bob_speed;
uniform float u_cam_bob;
uniform vec3  u_lamp_color;
uniform vec3  u_eq_color_low;
uniform vec3  u_eq_color_high;
uniform vec3  u_wall_color;
uniform vec3  u_edge_color;
uniform vec4  u_wall_fit;
uniform vec4  u_floor_fit;
uniform float u_wall_fit_contain;
uniform float u_floor_fit_contain;
uniform float u_light_intensity;
uniform float u_wall_vividness;
uniform float u_bar_count;
uniform float u_has_wall_tex;
uniform float u_has_floor_tex;

uniform sampler2D u_bars;
uniform sampler2D u_peaks;
uniform sampler2D u_wallpaper;
uniform sampler2D u_floor;

out vec4 frag_color;

mat2 rot(float a) {{
    float s = sin(a), c = cos(a);
    return mat2(c, -s, s, c);
}}

float edgeMask(float distToEdge) {{
    return smoothstep(EDGE_WIDTH, EDGE_WIDTH + EDGE_SOFT, distToEdge);
}}

vec3 lampColor(int i) {{
    return u_lamp_color;
}}

vec3 lampPos(int i) {{
    float z = (float(i) - 1.5) * u_room_w * 0.4;
    return vec3(0.0, u_room_h - 0.05, z);
}}

vec2 panelHalf(int i) {{
    return vec2(PANEL_LONG, PANEL_SHORT);
}}

float sdBox2(vec2 q, vec2 h) {{
    vec2 d = abs(q) - h;
    return length(max(d, 0.0)) + min(max(d.x, d.y), 0.0);
}}

float sampleBarLevel(float barIndex, float wallID) {{
    return texelFetch(u_bars, ivec2(int(barIndex), int(wallID)), 0).r;
}}

vec3 lightAt(vec3 p, vec3 n, float bass) {{
    vec3 acc = vec3(0.0);
    for (int i = 0; i < 4; i++) {{
        vec3 lp = lampPos(i);
        lp.x = clamp(p.x, lp.x - PANEL_LONG, lp.x + PANEL_LONG);
        vec3 ld = lp - p;
        float d = length(ld);
        float diff = max(dot(n, ld / d), 0.0);
        float atten = LAMP_INTENSITY / (4.0 + d * d * 0.30);
        acc += lampColor(i) * diff * atten * (0.85 + bass * LAMP_BASS_PULSE);
    }}
    return acc * u_light_intensity + vec3(AMBIENT);
}}

vec3 sampleFittedTex(
    sampler2D tex,
    vec2 dstUV,
    vec4 fit,
    float containMode,
    vec3 proc,
    float useTex,
    float gain
) {{
    if (useTex < 0.5) {{
        return proc;
    }}
    vec2 tuv = (dstUV - fit.zw) / fit.xy;
    bool inside = tuv.x >= 0.0 && tuv.x <= 1.0 && tuv.y >= 0.0 && tuv.y <= 1.0;
    if (containMode > 0.5 && !inside) {{
        return proc;
    }}
    return texture(tex, clamp(tuv, 0.0, 1.0)).rgb * gain;
}}

vec3 floorMaterial(vec2 xz, float useFloorTex) {{
    float fu = xz.x / (u_room_w * 2.0) + 0.5;
    float fv = xz.y / (u_room_w * 2.0) + 0.5;

    vec2 tileUV = xz / FLOOR_TILE_SIZE;
    vec2 tileID = floor(tileUV);
    vec2 f = fract(tileUV);

    float grout = smoothstep(0.0, GROUT_WIDTH, f.x) * smoothstep(1.0, 1.0 - GROUT_WIDTH, f.x)
                * smoothstep(0.0, GROUT_WIDTH, f.y) * smoothstep(1.0, 1.0 - GROUT_WIDTH, f.y);

    float h = fract(sin(dot(tileID, vec2(127.1, 311.7))) * 43758.5453);
    vec3 tile = vec3(0.055, 0.055, 0.065) * (0.8 + h * 0.4);
    vec3 proc = mix(vec3(0.02), tile, grout);

    return sampleFittedTex(
        u_floor,
        vec2(fu, fv),
        u_floor_fit,
        u_floor_fit_contain,
        proc,
        useFloorTex,
        0.35
    );
}}

vec3 wallpaper(vec2 dstUV, float useTex) {{
    float m = sin(dstUV.x * 5.1) * sin(dstUV.y * 3.7);
    vec3 proc = u_wall_color * (1.0 + m * 0.03);
    return sampleFittedTex(
        u_wallpaper,
        dstUV,
        u_wall_fit,
        u_wall_fit_contain,
        proc,
        useTex,
        1.0
    );
}}

vec3 shadeWall(vec3 p, int wallID, vec3 n, float bass, float useTex) {{
    float u = (wallID < 2) ? p.z : p.x;
    float localU = (u / u_room_w) * 0.5 + 0.5;
    float v = p.y / u_room_h;

    vec3 paper = wallpaper(vec2(localU, 1.0 - v), useTex);
    vec3 col = paper * lightAt(p, n, bass) * u_wall_vividness;

    if (u_bar_count >= 0.5 && v > EQ_BOTTOM && v < EQ_TOP) {{
        float vv = (v - EQ_BOTTOM) / (EQ_TOP - EQ_BOTTOM);
        float bc = u_bar_count;

        float barIndex = min(floor(localU * bc), bc - 1.0);
        float audio = sampleBarLevel(barIndex, float(wallID));

        float peak = texelFetch(u_peaks, ivec2(int(barIndex), wallID), 0).r;

        float freqX = barIndex / max(bc - 1.0, 1.0);
        vec3 eqColor = mix(u_eq_color_low, u_eq_color_high, freqX);

        float ledRaw = vv * NUM_LEDS;
        float ledIndex = floor(ledRaw);
        float isLit = step(ledIndex, audio * NUM_LEDS);

        vec2 gridUV = fract(vec2(localU * bc, ledRaw));
        float blockMask = step(EQ_GAP, gridUV.x) * step(gridUV.x, 1.0 - EQ_GAP) *
                  step(EQ_GAP, gridUV.y) * step(gridUV.y, 1.0 - EQ_GAP);

        vec3 ledColor = mix(eqColor, vec3(1.0), ledIndex / NUM_LEDS * 0.8);
        vec3 leds = ledColor * EQ_BRIGHT * isLit;

        float capIndex = clamp(floor(peak * NUM_LEDS), 0.0, NUM_LEDS - 1.0);
        float isCap = 1.0 - min(abs(ledIndex - capIndex), 1.0);
        isCap *= step(audio * NUM_LEDS, capIndex + 1.0);
        isCap *= smoothstep(0.06, 0.14, peak);
        vec3 capColor = mix(eqColor, vec3(1.0), 0.45) * 1.8;
        leds = mix(leds, capColor, isCap);

        col += leds * blockMask;

        float litRegion = smoothstep(audio + 0.08, audio - 0.05, vv);
        col += eqColor * litRegion * EQ_GLOW * (0.5 + audio);
    }}

    float dCorner = u_room_w - abs(u);
    float dHoriz  = min(p.y, u_room_h - p.y);
    col = mix(u_edge_color, col, edgeMask(min(dCorner, dHoriz)));
    return col;
}}

vec3 shadeCeiling(vec3 p, float bass) {{
    vec3 col = vec3(0.028, 0.028, 0.035);
    for (int i = 0; i < 4; i++) {{
        float d = sdBox2(p.xz - lampPos(i).xz, panelHalf(i));
        float panel = smoothstep(PANEL_EDGE, -PANEL_EDGE, d);
        float core = smoothstep(0.0, -min(PANEL_SHORT, PANEL_LONG) * 0.8, d);
        float glow = 0.30 / (0.3 + max(d, 0.0) * max(d, 0.0) * 2.5);
        col += lampColor(i) * u_light_intensity * (panel * (PANEL_BRIGHT + bass * 2.5)
                             + core * 0.8
                             + glow * (0.45 + bass));
    }}
    float dWall = u_room_w - max(abs(p.x), abs(p.z));
    col = mix(u_edge_color, col, edgeMask(dWall));
    return col;
}}

vec3 shadeFloorBase(vec3 p, float bass, float useFloorTex) {{
    vec3 n = vec3(0.0, 1.0, 0.0);
    vec3 alb = floorMaterial(p.xz, useFloorTex);
    vec3 col = alb * lightAt(p, n, bass);

    for (int i = 0; i < 4; i++) {{
        float spread = u_room_h * CONE_SPREAD;
        float d = sdBox2(p.xz - lampPos(i).xz, panelHalf(i));
        float pool = smoothstep(spread, spread * 0.15, d);
        col += lampColor(i) * u_light_intensity * pool * POOL_STRENGTH * (0.7 + bass);
    }}
    float dWall = u_room_w - max(abs(p.x), abs(p.z));
    col = mix(u_edge_color, col, edgeMask(dWall));
    return col;
}}

float roomHit(vec3 ro, vec3 rd, out int face) {{
    float tx = ((rd.x > 0.0 ? u_room_w : -u_room_w) - ro.x) / rd.x;
    float tz = ((rd.z > 0.0 ? u_room_w : -u_room_w) - ro.z) / rd.z;
    float ty = ((rd.y > 0.0 ? u_room_h : 0.0)     - ro.y) / rd.y;
    if (tx < tz && tx < ty) {{ face = 0; return tx; }}
    if (tz < ty)            {{ face = 1; return tz; }}
    face = 2; return ty;
}}

void main() {{
    float px = gl_FragCoord.x - u_origin.x;
    float py = (u_canvas_h - gl_FragCoord.y) - u_origin.y;
    if (px < 0.0 || px >= u_res.x || py < 0.0 || py >= u_res.y) discard;

    vec2 uv = (vec2(px, u_res.y - py) - u_res * 0.5) / u_res.y;

    float bass = sampleBarLevel(1.0, 0.0);
    if (bass < 0.01) bass = (sin(u_t * 2.0) * 0.5 + 0.5) * 0.2;
    bass *= bass;

    vec3 ro = vec3(0.0, CAM_H + sin(u_t * u_bob_speed * 0.7) * u_cam_bob, 0.0);
    vec3 rd = normalize(vec3(uv, FOV));
    rd.yz *= rot(-CAM_PITCH);            // camera's own fixed lean (screen-space)
    rd.xz *= rot(u_t * u_rot_speed);

    float pitch = CAM_PITCH + sin(u_t * u_bob_speed) * u_bob_amt;
    rd.yz *= rot(-pitch);
    rd.xz *= rot(u_t * u_rot_speed);

    float tilt = ROOM_TILT + sin(u_t * TILT_SPEED) * TILT_WOBBLE;
    rd.yz *= rot(tilt);

    vec3 col = vec3(0.0);
    float weight = 1.0;
    float firstT = 0.0;
    vec3 o = ro, d = rd;

    for (int bounce = 0; bounce < 2; bounce++) {{
        int face;
        float t = roomHit(o, d, face);
        vec3 p = o + d * t;
        if (bounce == 0) firstT = t;

        if (face == 2 && d.y > 0.0) {{
            col += weight * shadeCeiling(p, bass);
            break;
        }}
        else if (face == 2) {{
            col += weight * shadeFloorBase(p, bass, u_has_floor_tex);
            if (bounce == 0 && FLOOR_REFLECT > 0.0) {{
                weight *= FLOOR_REFLECT;
                o = p + vec3(0.0, 0.001, 0.0);
                d = reflect(d, vec3(0.0, 1.0, 0.0));
                continue;
            }}
            break;
        }}
        else {{
            int wallID; vec3 n;
            if (face == 0) {{
                wallID = d.x > 0.0 ? 0 : 1;
                n = vec3(d.x > 0.0 ? -1.0 : 1.0, 0.0, 0.0);
            }} else {{
                wallID = d.z > 0.0 ? 2 : 3;
                n = vec3(0.0, 0.0, d.z > 0.0 ? -1.0 : 1.0);
            }}
            col += weight * shadeWall(p, wallID, n, bass, u_has_wall_tex);
            break;
        }}
    }}

    for (int s = 0; s < CONE_STEPS; s++) {{
        float ts = firstT * (float(s) + 0.5) / float(CONE_STEPS);
        vec3 q = ro + rd * ts;
        for (int i = 0; i < 4; i++) {{
            vec3 lp = lampPos(i);
            float widen = (lp.y - q.y) * CONE_SPREAD;
            float dR = sdBox2(q.xz - lp.xz, panelHalf(i)) - widen;
            float dens = smoothstep(0.0, -0.35, dR);
            dens *= smoothstep(0.0, 0.5, q.y) * (q.y / u_room_h);
            col += lampColor(i) * u_light_intensity * dens * CONE_STRENGTH * (firstT / float(CONE_STEPS))
                   * (0.7 + bass * LAMP_BASS_PULSE);
        }}
    }}

    col *= EXPOSURE;
    col *= exp(-firstT * FOG);
    col *= 1.0 - dot(uv, uv) * VIGNETTE;
    frag_color = vec4(sqrt(max(col, 0.0)), 1.0);
}}
"""

_QUAD = np.array(
    [-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0],
    dtype="f4",
)

_BLACK_RGB = np.zeros((1, 1, 3), dtype=np.uint8)


def _has_user_image(rgb: np.ndarray) -> bool:
    h, w, _ = rgb.shape
    return w > 1 or h > 1


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


def _prepare_rgb_from_pil(
    pil_img: PILImage.Image, *, max_px: int | None = None
) -> np.ndarray | None:
    w, h = pil_img.size
    if w < _MIN_DIM or h < _MIN_DIM:
        return None
    aspect = w / h if h else 0.0
    if aspect < _MIN_ASPECT or aspect > _MAX_ASPECT:
        return None
    cap = max_px if max_px is not None else _MAX_DIM
    if max(w, h) > cap:
        pil_img = pil_img.copy()
        pil_img.thumbnail((cap, cap), PILImage.Resampling.LANCZOS)
    return np.array(pil_img.convert("RGB"), dtype=np.uint8)


def _load_user_source_rgb(
    source: str,
    ctx: PrepareContext,
    clip_id: str,
    clip_type: str,
    field: str,
    *,
    max_px: int | None = None,
) -> np.ndarray | None:
    trimmed = source.strip()
    try:
        if trimmed.startswith(("http://", "https://")):
            local_path = resolve_source_sync(trimmed, ctx)
        else:
            local_path = resolve_local_source_path(trimmed)
    except Exception as exc:
        record_prepare_asset_failure(
            ctx,
            kind="clip",
            ref_id=clip_id,
            clip_type=clip_type,
            field=field,
            source=source,
            exc=exc,
        )
        log.warning("MusicRoomGL %s: could not resolve %s %r — %s", clip_id, field, source, exc)
        return None

    reason = _validate_source_path(local_path)
    if reason:
        record_prepare_asset_failure(
            ctx,
            kind="clip",
            ref_id=clip_id,
            clip_type=clip_type,
            field=field,
            source=source,
            exc=ValueError(reason),
            code=reason,
        )
        return None

    try:
        pil_img = PILImage.open(str(local_path))
        rgb = _prepare_rgb_from_pil(pil_img, max_px=max_px)
    except Exception as exc:
        record_prepare_asset_failure(
            ctx,
            kind="clip",
            ref_id=clip_id,
            clip_type=clip_type,
            field=field,
            source=source,
            exc=exc,
            code="load_failed",
        )
        log.warning("MusicRoomGL %s: failed to load %s %r — %s", clip_id, field, local_path, exc)
        return None

    if rgb is None:
        record_prepare_asset_failure(
            ctx,
            kind="clip",
            ref_id=clip_id,
            clip_type=clip_type,
            field=field,
            source=source,
            exc=ValueError("dimensions_or_aspect"),
            code="invalid_dimensions",
        )
    return rgb


_WALLS_IDX = np.arange(_NUM_WALLS, dtype=np.float32)


def _bar_sample_indices(n_bars: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if n_bars <= 0:
        empty = np.zeros((0, _NUM_WALLS), dtype=np.int32)
        return empty, empty, np.zeros((0, _NUM_WALLS), dtype=np.float32)
    bars_idx = np.arange(n_bars, dtype=np.float32)
    freq_x = bars_idx / n_bars
    sample_pos = (freq_x[:, None] + _WALLS_IDX[None, :] * 0.25) % 1.0
    bin_i0 = np.floor(sample_pos * (N_SPECTRUM - 1)).astype(np.int32)
    bin_i1 = np.minimum(bin_i0 + 1, N_SPECTRUM - 1)
    bin_frac = sample_pos * (N_SPECTRUM - 1) - bin_i0
    return bin_i0, bin_i1, bin_frac.astype(np.float32)


def _bars_from_spectrum(spec: np.ndarray, n_bars: int = _MAX_BARS) -> np.ndarray:
    """Map spectrum (..., 64) to bar levels (..., n_bars, 4)."""
    if n_bars <= 0:
        shape = spec.shape[:-1] + (0, _NUM_WALLS)
        return np.zeros(shape, dtype=np.float32)
    i0, i1, frac = _bar_sample_indices(n_bars)
    s0 = np.take(spec, i0, axis=-1)
    s1 = np.take(spec, i1, axis=-1)
    audio = s0 * (1.0 - frac) + s1 * frac
    return np.clip(audio * audio * 1.5, 0.0, 1.2).astype(np.float32)


def _pad_bars_texture(bars: np.ndarray) -> np.ndarray:
    """Pad (..., n_bars, 4) to (..., MAX_BARS, 4) for GPU upload."""
    n = bars.shape[-2]
    if n == _MAX_BARS:
        return bars
    if n == 0:
        return np.zeros(bars.shape[:-2] + (_MAX_BARS, _NUM_WALLS), dtype=np.float32)
    pad = np.zeros(bars.shape[:-2] + (_MAX_BARS - n, _NUM_WALLS), dtype=np.float32)
    return np.concatenate([bars, pad], axis=-2)


def _bars_texture_bytes(bars: np.ndarray) -> bytes:
    """Pack (..., bars, walls) for a GL texture sized (MAX_BARS, NUM_WALLS)."""
    data = np.ascontiguousarray(bars, dtype=np.float32)
    return np.ascontiguousarray(np.swapaxes(data, -2, -1), dtype=np.float32).tobytes()


def _demo_spectrum_timeline(total_frames: int, fps: float) -> np.ndarray:
    t = np.arange(total_frames, dtype=np.float32) / max(fps, 1e-6)
    freq_x = np.arange(N_SPECTRUM, dtype=np.float32) / N_SPECTRUM
    wave = np.sin(t[:, None] * 4.0 + freq_x[None, :] * 10.0) * 0.5 + 0.5
    return np.clip((wave * 0.3) ** 2 * 1.5, 0.0, 1.2).astype(np.float32)


def _normalize_spectrum_timeline(frames: list[AudioBusFrame], n_bus: int) -> np.ndarray:
    if n_bus <= 0:
        return np.zeros((0, N_SPECTRUM), dtype=np.float32)
    raw = np.stack(
        [np.clip(np.asarray(frames[f].spectrum, dtype=np.float32), 0.0, 1.0) for f in range(n_bus)],
        axis=0,
    )
    out = np.empty_like(raw)
    for col in range(N_SPECTRUM):
        channel = raw[:, col]
        lo, hi = np.percentile(channel, (5.0, 95.0))
        span = max(float(hi - lo), 1e-6)
        out[:, col] = np.clip((channel - lo) / span, 0.0, 1.0)
    return out


def _smooth_spectrum_timeline(raw: np.ndarray, smoothing: float) -> np.ndarray:
    """EMA over time; raw shape (F, 64)."""
    if raw.size == 0:
        return raw
    out = np.empty_like(raw)
    smoothed = np.zeros(N_SPECTRUM, dtype=np.float32)
    s = smoothing
    one_minus_s = 1.0 - s
    for f in range(raw.shape[0]):
        smoothed = smoothed * s + raw[f] * one_minus_s
        out[f] = smoothed
    return out


def _peak_hold_timeline(bars: np.ndarray, fps: float) -> np.ndarray:
    """Peak caps with hold/fall; bars shape (F, n_bars, 4)."""
    total = bars.shape[0]
    if total == 0:
        return bars
    n_bars = bars.shape[1]
    delta = 1.0 / max(fps, 1e-6)
    peak_history = np.zeros_like(bars)
    peak = np.zeros((n_bars, _NUM_WALLS), dtype=np.float32)
    timer = np.zeros((n_bars, _NUM_WALLS), dtype=np.float32)
    for f in range(total):
        audio = bars[f]
        timer += delta
        falling = timer > _PEAK_HOLD
        peak = np.where(falling, peak - _PEAK_FALL * delta, peak)
        newer = audio >= peak
        peak = np.where(newer, audio, peak)
        timer = np.where(newer, 0.0, timer)
        peak_history[f] = np.clip(peak, 0.0, 1.2)
    return peak_history


def _precompute_bars_and_peaks(
    *,
    total_frames: int,
    fps: float,
    sensitivity: float,
    bus_frames: list[AudioBusFrame] | None,
    bar_count: int = _MAX_BARS,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (bar_history[F,MAX_BARS,4], peak_history[F,MAX_BARS,4])."""
    if total_frames <= 0 or bar_count <= 0:
        empty = np.zeros((max(total_frames, 0), _MAX_BARS, _NUM_WALLS), dtype=np.float32)
        return empty, empty.copy()

    n_bus = len(bus_frames) if bus_frames else 0
    if n_bus > 0:
        assert bus_frames is not None
        normalized = _normalize_spectrum_timeline(bus_frames, n_bus)
        raw = np.zeros((total_frames, N_SPECTRUM), dtype=np.float32)
        n_copy = min(total_frames, n_bus)
        raw[:n_copy] = np.clip(normalized[:n_copy] * float(sensitivity), 0.0, 1.0)
        if n_copy < total_frames:
            raw[n_copy:] = _demo_spectrum_timeline(total_frames - n_copy, fps)
        spectrum = _smooth_spectrum_timeline(raw, _SMOOTHING)
    else:
        spectrum = _demo_spectrum_timeline(total_frames, fps)

    bars = _bars_from_spectrum(spectrum, bar_count)
    peaks = _peak_hold_timeline(bars, fps)
    return _pad_bars_texture(bars), _pad_bars_texture(peaks)


def _fit_uv_transform(
    fit: FitMode,
    src_w: float,
    src_h: float,
    dst_w: float,
    dst_h: float,
) -> tuple[tuple[float, float, float, float], float]:
    """Map destination UV [0,1]² to source texture UV [0,1]² (scale, offset per axis)."""
    if src_w <= 0 or src_h <= 0 or dst_w <= 0 or dst_h <= 0:
        return (1.0, 1.0, 0.0, 0.0), 0.0

    src_aspect = src_w / src_h
    dst_aspect = dst_w / dst_h

    match fit:
        case FitMode.CONTAIN:
            s = dst_w / src_w if src_aspect > dst_aspect else dst_h / src_h
            draw_w = src_w * s
            draw_h = src_h * s
        case FitMode.COVER:
            s = dst_h / src_h if src_aspect > dst_aspect else dst_w / src_w
            draw_w = src_w * s
            draw_h = src_h * s
        case FitMode.FIT_WIDTH:
            s = dst_w / src_w
            draw_w = dst_w
            draw_h = src_h * s
        case FitMode.FIT_HEIGHT:
            s = dst_h / src_h
            draw_w = src_w * s
            draw_h = dst_h
        case _:  # STRETCH
            draw_w = dst_w
            draw_h = dst_h

    scale_u = draw_w / dst_w
    scale_v = draw_h / dst_h
    offset_u = (1.0 - scale_u) / 2.0
    offset_v = (1.0 - scale_v) / 2.0
    contain = 1.0 if fit == FitMode.CONTAIN else 0.0
    return (scale_u, scale_v, offset_u, offset_v), contain


class MusicRoomGL(AudioVisualMixin, ClipGL):
    """Raymarched music room with wall EQ, ceiling panels, and bass-reactive lighting."""

    clip_type: ClassVar[str] = "std-music-room-gl"
    clip_category: ClassVar[ClipCategory] = ClipCategory.BACKGROUND
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED, ClipTag.GL, ClipTag.AUDIO_REACTIVE]
    clip_presets: ClassVar[list[ClipPreset]] = [
        ClipPreset(id="default", label="Neon Room", values={}),
        ClipPreset(
            id="slow_lounge",
            label="Slow Lounge",
            values={
                "color": ColorToken.PRIMARY.value,
                "room_width": 7.0,
                "room_height": 6.0,
                "spin_speed": 0.15,
                "motion": 0.5,
            },
        ),
        ClipPreset(
            id="club",
            label="Club Spin",
            values={
                "color": ColorToken.SECONDARY.value,
                "eq_color_low": ColorToken.PRIMARY.value,
                "eq_color_high": ColorToken.ACCENT.value,
                "room_width": 9.0,
                "room_height": 4.5,
                "spin_speed": 0.65,
                "motion": 1.2,
            },
        ),
    ]

    color: ColorToken | Color = color_field(
        ColorToken.PRIMARY,
        default=Color(_DEFAULT_LAMP_HEX),
        description="Ceiling lamp, panel, and volumetric light color",
    )
    eq_color_low: ColorToken | Color = color_field(
        ColorToken.PRIMARY,
        description="Wall EQ bar color at the bass (left) end",
    )
    eq_color_high: ColorToken | Color = color_field(
        ColorToken.SECONDARY,
        description="Wall EQ bar color at the treble (right) end",
    )
    room_width: float = Field(
        default=8.0,
        ge=5.0,
        le=12.0,
        multiple_of=0.5,
        description="Room half-width in world units",
    )
    room_height: float = Field(
        default=5.0,
        ge=3.0,
        le=8.0,
        multiple_of=0.5,
        description="Ceiling height in world units",
    )
    spin_speed: float = Field(
        default=_ROT_SPEED_DEFAULT,
        ge=0.0,
        le=1.0,
        multiple_of=0.05,
        description="Continuous camera yaw speed (0 = no spin)",
    )
    motion: float = Field(
        default=1.0,
        ge=0.0,
        le=2.0,
        multiple_of=0.1,
        description="Camera bob intensity (pitch and vertical sway)",
    )
    light_intensity: float = Field(
        default=1.0,
        ge=0.1,
        le=2.0,
        multiple_of=0.05,
        description="Lamp, ceiling panel, ambient, and volumetric brightness",
    )
    bar_count: int = Field(
        default=_MAX_BARS,
        ge=0,
        le=_MAX_BARS,
        multiple_of=1,
        description="LED columns per wall (0 = no EQ display)",
    )
    wall_source: str | None = stock_image_field(
        default=None,
        description="Optional wallpaper image for all four walls (local path or http(s) URL)",
    )
    wall_fit: FitMode = Field(
        default=FitMode.COVER,
        description="How the wall image fills each wall face",
    )
    wall_vividness: float = Field(
        default=_WALL_VIVIDNESS_DEFAULT,
        ge=0.5,
        le=5.0,
        multiple_of=0.01,
        description="How strongly the wall image keeps its original color under room lighting",
    )
    floor_source: str | None = stock_image_field(
        default=None,
        description="Optional floor tile image (local path or http(s) URL)",
    )
    floor_fit: FitMode = Field(
        default=FitMode.COVER,
        description="How the floor image fills the floor plane",
    )
    wall_source_attribution: str = stock_attribution_field("wall_source")
    wall_source_provider: str = stock_provider_field("wall_source")
    floor_source_attribution: str = stock_attribution_field("floor_source")
    floor_source_provider: str = stock_provider_field("floor_source")

    @classmethod
    def file_upload_policies(cls) -> dict[str, JobBoundsFactorPolicy]:
        policy = JobBoundsFactorPolicy(factor=_TEXTURE_MAX_DIM_FACTOR)
        return {
            "wall_source": policy,
            "floor_source": policy,
        }

    @classmethod
    def texture_source_max_px(cls, bounds: Rect) -> int:
        return cls.file_upload_policies()["wall_source"].max_px_from_bounds(
            bounds.width, bounds.height
        )

    _canvas_h: float = PrivateAttr(default=0.0)
    _bounds_x: float = PrivateAttr(default=0.0)
    _bounds_y: float = PrivateAttr(default=0.0)
    _bounds_w: float = PrivateAttr(default=0.0)
    _bounds_h: float = PrivateAttr(default=0.0)

    _wall_rgb: np.ndarray = PrivateAttr(default_factory=lambda: _BLACK_RGB.copy())
    _floor_rgb: np.ndarray = PrivateAttr(default_factory=lambda: _BLACK_RGB.copy())
    _bar_history: np.ndarray = PrivateAttr(
        default_factory=lambda: np.zeros((0, _MAX_BARS, _NUM_WALLS), dtype=np.float32)
    )
    _peak_history: np.ndarray = PrivateAttr(
        default_factory=lambda: np.zeros((0, _MAX_BARS, _NUM_WALLS), dtype=np.float32)
    )

    _program: moderngl.Program | None = PrivateAttr(default=None)
    _vao: moderngl.VertexArray | None = PrivateAttr(default=None)
    _shader_revision: int = PrivateAttr(default=0)
    _wall_tex: moderngl.Texture | None = PrivateAttr(default=None)
    _floor_tex: moderngl.Texture | None = PrivateAttr(default=None)
    _bars_tex: moderngl.Texture | None = PrivateAttr(default=None)
    _peak_tex: moderngl.Texture | None = PrivateAttr(default=None)

    async def prepare(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        await asyncio.to_thread(self._prepare_sync, ctx, bounds)

    def _prepare_sync(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        b = bounds or Rect(0, 0, ctx.job.width, ctx.job.height)
        self._canvas_h = float(ctx.job.height)
        self._bounds_x = float(b.x)
        self._bounds_y = float(b.y)
        self._bounds_w = float(b.width)
        self._bounds_h = float(b.height)

        self._wall_rgb = _BLACK_RGB.copy()
        self._floor_rgb = _BLACK_RGB.copy()
        texture_max_px = self.texture_source_max_px(b)
        if self.wall_source and self.wall_source.strip():
            loaded = _load_user_source_rgb(
                self.wall_source.strip(),
                ctx,
                self.id,
                self.clip_type,
                "wall_source",
                max_px=texture_max_px,
            )
            if loaded is not None:
                self._wall_rgb = loaded
        if self.floor_source and self.floor_source.strip():
            loaded = _load_user_source_rgb(
                self.floor_source.strip(),
                ctx,
                self.id,
                self.clip_type,
                "floor_source",
                max_px=texture_max_px,
            )
            if loaded is not None:
                self._floor_rgb = loaded

        bus_frames = self.bus_timeline(ctx)
        self._bar_history, self._peak_history = _precompute_bars_and_peaks(
            total_frames=max(ctx.job.total_frames, 0),
            fps=float(ctx.job.fps),
            sensitivity=float(self.sensitivity),
            bus_frames=bus_frames,
            bar_count=int(self.bar_count),
        )

        self._wall_tex = None
        self._floor_tex = None
        self._bars_tex = None
        self._peak_tex = None

    def _bars_for_frame(self, ctx: RenderContext) -> np.ndarray:
        if self._bar_history.shape[0] > 0:
            f = max(0, min(ctx.time.frame, self._bar_history.shape[0] - 1))
            return self._bar_history[f]
        if self.bus_active_for_draw(ctx):
            spec = np.clip(
                np.asarray(ctx.audio_bus_frame.spectrum, dtype=np.float32)
                * float(self.sensitivity),
                0.0,
                1.0,
            )
            return _pad_bars_texture(_bars_from_spectrum(spec, int(self.bar_count)))
        return _pad_bars_texture(
            _bars_from_spectrum(
                _demo_spectrum_timeline(1, float(ctx.job.fps))[0], int(self.bar_count)
            )
        )

    def _ensure_program(self, gl: moderngl.Context) -> None:
        if self._program is not None and self._shader_revision == _SHADER_REVISION:
            return
        self._program = gl.program(vertex_shader=_VERT, fragment_shader=_FRAG)
        vbo = gl.buffer(_QUAD.tobytes())
        self._vao = gl.simple_vertex_array(self._program, vbo, "in_vert")
        self._shader_revision = _SHADER_REVISION
        self._wall_tex = None
        self._floor_tex = None
        self._bars_tex = None
        self._peak_tex = None

    def _peaks_for_frame(self, ctx: RenderContext) -> np.ndarray:
        if self._peak_history.shape[0] > 0:
            f = max(0, min(ctx.time.frame, self._peak_history.shape[0] - 1))
            return self._peak_history[f]
        return self._bars_for_frame(ctx)

    def _ensure_wall_texture(self, gl: moderngl.Context) -> None:
        if self._wall_tex is not None:
            return
        h, w, _ = self._wall_rgb.shape
        self._wall_tex = gl.texture((w, h), 3, self._wall_rgb.tobytes())
        self._wall_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
        clamp = w > 1 or h > 1
        self._wall_tex.repeat_x = not clamp
        self._wall_tex.repeat_y = not clamp

    def _ensure_floor_texture(self, gl: moderngl.Context) -> None:
        if self._floor_tex is not None:
            return
        h, w, _ = self._floor_rgb.shape
        self._floor_tex = gl.texture((w, h), 3, self._floor_rgb.tobytes())
        self._floor_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
        clamp = w > 1 or h > 1
        self._floor_tex.repeat_x = not clamp
        self._floor_tex.repeat_y = not clamp

    def _ensure_frame_textures(
        self,
        gl: moderngl.Context,
        bars: np.ndarray,
        peaks: np.ndarray,
    ) -> None:
        bars_data = np.ascontiguousarray(bars, dtype=np.float32)
        peak_data = np.ascontiguousarray(peaks, dtype=np.float32)

        if self._bars_tex is None:
            self._bars_tex = gl.texture((_MAX_BARS, _NUM_WALLS), 1, dtype="f4")
            self._bars_tex.filter = (moderngl.NEAREST, moderngl.NEAREST)
        self._bars_tex.write(_bars_texture_bytes(bars_data))

        if self._peak_tex is None:
            self._peak_tex = gl.texture((_MAX_BARS, _NUM_WALLS), 1, dtype="f4")
            self._peak_tex.filter = (moderngl.NEAREST, moderngl.NEAREST)
        self._peak_tex.write(_bars_texture_bytes(peak_data))

    def _set_uniform(self, prog: moderngl.Program, name: str, value: Any) -> None:
        if name not in prog:
            return
        member = prog[name]
        if isinstance(member, moderngl.Uniform):
            member.value = value

    def draw(self, ctx: RenderContext) -> None:
        gl: moderngl.Context = ctx.canvas
        self._ensure_program(gl)
        self._ensure_wall_texture(gl)
        self._ensure_floor_texture(gl)

        bars = self._bars_for_frame(ctx)
        peaks = self._peaks_for_frame(ctx)
        self._ensure_frame_textures(gl, bars, peaks)

        prog = self._program
        assert prog is not None
        assert self._wall_tex is not None
        assert self._floor_tex is not None
        assert self._bars_tex is not None
        assert self._peak_tex is not None

        lr, lg, lb, _ = resolve_color(self.color, ctx.job.colors).rgba
        elr, elg, elb, _ = resolve_color(self.eq_color_low, ctx.job.colors).rgba
        ehr, ehg, ehb, _ = resolve_color(self.eq_color_high, ctx.job.colors).rgba

        self._set_uniform(prog, "u_res", (self._bounds_w, self._bounds_h))
        self._set_uniform(prog, "u_origin", (self._bounds_x, self._bounds_y))
        self._set_uniform(prog, "u_canvas_h", self._canvas_h)
        self._set_uniform(prog, "u_t", float(ctx.time.t))
        self._set_uniform(prog, "u_room_w", float(self.room_width))
        self._set_uniform(prog, "u_room_h", float(self.room_height))
        self._set_uniform(prog, "u_rot_speed", float(self.spin_speed))
        self._set_uniform(prog, "u_bob_amt", _BOB_AMT_BASE * float(self.motion))
        self._set_uniform(prog, "u_bob_speed", _BOB_SPEED_BASE)
        self._set_uniform(prog, "u_cam_bob", _CAM_BOB_BASE * float(self.motion))
        self._set_uniform(prog, "u_lamp_color", (lr, lg, lb))
        self._set_uniform(prog, "u_eq_color_low", (elr, elg, elb))
        self._set_uniform(prog, "u_eq_color_high", (ehr, ehg, ehb))
        self._set_uniform(prog, "u_light_intensity", float(self.light_intensity))
        self._set_uniform(prog, "u_wall_vividness", float(self.wall_vividness))
        self._set_uniform(prog, "u_bar_count", float(self.bar_count))
        self._set_uniform(prog, "u_has_wall_tex", 1.0 if _has_user_image(self._wall_rgb) else 0.0)
        self._set_uniform(prog, "u_has_floor_tex", 1.0 if _has_user_image(self._floor_rgb) else 0.0)
        self._set_uniform(prog, "u_wall_color", _WALL_COLOR)
        self._set_uniform(prog, "u_edge_color", _EDGE_COLOR)

        wall_h, wall_w, _ = self._wall_rgb.shape
        wall_dst_w = 2.0 * float(self.room_width)
        wall_dst_h = float(self.room_height)
        wall_fit, wall_contain = _fit_uv_transform(
            self.wall_fit, float(wall_w), float(wall_h), wall_dst_w, wall_dst_h
        )
        self._set_uniform(prog, "u_wall_fit", wall_fit)
        self._set_uniform(prog, "u_wall_fit_contain", wall_contain)

        floor_h, floor_w, _ = self._floor_rgb.shape
        floor_side = 2.0 * float(self.room_width)
        floor_fit, floor_contain = _fit_uv_transform(
            self.floor_fit, float(floor_w), float(floor_h), floor_side, floor_side
        )
        self._set_uniform(prog, "u_floor_fit", floor_fit)
        self._set_uniform(prog, "u_floor_fit_contain", floor_contain)

        self._bars_tex.use(0)
        self._peak_tex.use(1)
        self._wall_tex.use(2)
        self._floor_tex.use(3)
        self._set_uniform(prog, "u_bars", 0)
        self._set_uniform(prog, "u_peaks", 1)
        self._set_uniform(prog, "u_wallpaper", 2)
        self._set_uniform(prog, "u_floor", 3)

        gl.scissor = (
            int(self._bounds_x),
            int(ctx.job.height - self._bounds_y - self._bounds_h),
            int(self._bounds_w),
            int(self._bounds_h),
        )

        assert self._vao is not None
        self._vao.render(moderngl.TRIANGLES)

        gl.scissor = None
