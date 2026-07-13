"""Neon synthwave horizon — sunset sky, infinite road grid, and spectrum-driven EQ silhouette.

Adapted from Shadertoy "Neon Sunset" (CC0).
"""

from __future__ import annotations

from typing import Any, ClassVar

import moderngl
import numpy as np
from pydantic import Field, PrivateAttr

from pixfabrica_core.audio.bus import N_SPECTRUM, AudioBusFrame
from pixfabrica_core.audio.mixin import AudioVisualMixin
from pixfabrica_core.clips import ClipCategory, ClipGL, ClipTag, PrepareContext, RenderContext
from pixfabrica_core.graphics import Rect
from pixfabrica_core.theme.color import Color, ColorToken, color_field, resolve_color
from pixfabrica_std.mesh.shader_helper import precompute_bus_drives

# Preview caps — keep scrubbing responsive; final render uses the user's star_layers.
_PREVIEW_STAR_LAYERS_CAP = 3
_MAX_STAR_LAYERS = 5
_ROAD_OFF = 20.0
_SPECTRUM_SMOOTHING = 0.35
_SPECTRUM_GAIN = 2.2
_SHADER_REVISION = 6

_VERT = """
#version 330 core
in vec2 in_vert;
void main() { gl_Position = vec4(in_vert, 0.0, 1.0); }
"""

_FRAG = f"""
#version 330 core

#define MAX_STAR_LAYERS {_MAX_STAR_LAYERS}.0
#define PI 3.141592654
#define TAU (2.0 * PI)
#define ROAD_OFF {_ROAD_OFF}
#define EQ_BAR_SCALE 0.42

uniform vec2  u_res;
uniform vec2  u_origin;
uniform float u_canvas_h;
uniform float u_t;
uniform float u_speed;
uniform float u_star_layers;
uniform float u_sensitivity;
uniform float u_opacity;
uniform vec3  u_color_primary;
uniform vec3  u_color_secondary;
uniform vec3  u_color_accent;
uniform float u_bass;
uniform float u_mid;
uniform float u_high;
uniform float u_beat_decay;
uniform float u_amplitude;
uniform sampler2D u_spectrum;

out vec4 frag_color;

#define ROT(a) mat2(cos(a), sin(a), -sin(a), cos(a))

float sRGB(float t) {{
    return mix(1.055 * pow(t, 1.0 / 2.4) - 0.055, 12.92 * t, step(t, 0.0031308));
}}

vec3 sRGB(vec3 c) {{
    return vec3(sRGB(c.x), sRGB(c.y), sRGB(c.z));
}}

vec3 aces_approx(vec3 v) {{
    v = max(v, 0.0);
    v *= 0.6;
    float a = 2.51;
    float b = 0.03;
    float c = 2.43;
    float d = 0.59;
    float e = 0.14;
    return clamp((v * (a * v + b)) / (v * (c * v + d) + e), 0.0, 1.0);
}}

float hash(float co) {{
    return fract(sin(co * 12.9898) * 13758.5453);
}}

vec2 hash2(vec2 p) {{
    p = vec2(dot(p, vec2(127.1, 311.7)), dot(p, vec2(269.5, 183.3)));
    return fract(sin(p) * 43758.5453123);
}}

vec3 blackbody(float temp) {{
    vec3 col = vec3(255.0);
    col.x = 56100000.0 * pow(temp, -1.5) + 148.0;
    col.y = 100.04 * log(temp) - 623.6;
    if (temp > 6500.0) col.y = 35200000.0 * pow(temp, -1.5) + 184.0;
    col.z = 194.18 * log(temp) - 1448.6;
    col = clamp(col, 0.0, 255.0) / 255.0;
    if (temp < 1000.0) col *= temp / 1000.0;
    return col;
}}

const vec4 hsv2rgb_K = vec4(1.0, 2.0 / 3.0, 1.0 / 3.0, 3.0);

vec3 hsv2rgb(vec3 c) {{
    vec3 p = abs(fract(c.xxx + hsv2rgb_K.xyz) * 6.0 - hsv2rgb_K.www);
    return c.z * mix(hsv2rgb_K.xxx, clamp(p - hsv2rgb_K.xxx, 0.0, 1.0), c.y);
}}

#define HSV2RGB(c) (c.z * mix(hsv2rgb_K.xxx, clamp(abs(fract(c.xxx + hsv2rgb_K.xyz) * 6.0 - hsv2rgb_K.www) - hsv2rgb_K.xxx, 0.0, 1.0), c.y))

float tanh_approx(float x) {{
    float x2 = x * x;
    return clamp(x * (27.0 + x2) / (27.0 + 9.0 * x2), -1.0, 1.0);
}}

vec3 tanh3(vec3 x) {{
    return vec3(tanh_approx(x.x), tanh_approx(x.y), tanh_approx(x.z));
}}

vec3 themeTint(vec3 src, vec3 theme) {{
    return src * theme;
}}

// Preserve neon luma while shifting hue toward a theme token (road grid + EQ).
vec3 neonTheme(vec3 neon, vec3 theme) {{
    float l = max(dot(neon, vec3(0.299, 0.587, 0.114)), 1e-4);
    vec3 t = normalize(max(theme, vec3(0.05)));
    return t * l * 3.0;
}}

float circle(vec2 p, float r) {{
    return length(p) - r;
}}

float pmin(float a, float b, float k) {{
    float h = clamp(0.5 + 0.5 * (b - a) / k, 0.0, 1.0);
    return mix(b, a, h) - k * h * (1.0 - h);
}}

float mod1(inout float p, float size) {{
    float halfsize = size * 0.5;
    float c = floor((p + halfsize) / size);
    p = mod(p + halfsize, size) - halfsize;
    return c;
}}

vec2 mod2(inout vec2 p, vec2 size) {{
    vec2 c = floor((p + size * 0.5) / size);
    p = mod(p + size * 0.5, size) - size * 0.5;
    return c;
}}

float rayPlane(vec3 ro, vec3 rd, vec4 pl) {{
    return -(dot(ro, pl.xyz) + pl.w) / dot(rd, pl.xyz);
}}

vec3 toSpherical(vec3 p) {{
    float r = length(p);
    float t = acos(p.z / r);
    float ph = atan(p.y, p.x);
    return vec3(r, t, ph);
}}

float sun(vec2 p) {{
    return circle(p, 0.5);
}}

float segmentx(vec2 p) {{
    float d0 = abs(p.y);
    float d1 = length(p);
    return p.x > 0.0 ? d0 : d1;
}}

float segmentx(vec2 p, float l) {{
    float hl = 0.5 * l;
    p.x = abs(p.x);
    float d0 = abs(p.y);
    float d1 = length(p - vec2(hl, 0.0));
    return p.x > hl ? d1 : d0;
}}

float sampleSpectrum(float u) {{
    return texture(u_spectrum, vec2(clamp(u, 0.0, 1.0), 0.5)).r;
}}

float synth(vec2 p, float aa, out float h, out float db) {{
    const float z = 75.0;
    p.y -= -70.0;
    const float st = 0.04;
    p.x = abs(p.x);
    p.x -= 20.0 - 3.5;
    p.x += st * 20.0;
    p /= z;
    float n = mod1(p.x, st);
    float dib = 1e6;
    const int around = 0;
    for (int i = -around; i <= around; ++i) {{
        float specU = fract((n + float(i)) * st);
        float fft = sampleSpectrum(specU);
        fft *= fft;
        if (i == 0) h = fft;
        float barH = fft * EQ_BAR_SCALE + 0.028;
        float dibb = segmentx((p - vec2(st * float(i), 0.0)).yx, barH) - st * 0.4;
        dib = min(dib, dibb);
    }}

    float d = dib;
    db = abs(p.y) * z;
    return smoothstep(aa, -aa, d * z);
}}

vec3 road(vec3 ro, vec3 rd, vec3 nrd, float glare, vec4 pl, float time, out float pt) {{
    const float sm = 1.0;
    float off = abs(pl.w);
    float t = rayPlane(ro, rd, pl);
    pt = t;

    vec3 p = ro + rd * t;
    vec3 np = ro + nrd * t;

    vec2 pp = p.xz;
    vec2 npp = np.xz;
    vec2 opp = pp;

    float aa = length(npp - pp) * sqrt(0.5);
    float scroll = time * (1.0 + u_bass * u_sensitivity * 0.25);
    pp.y += -60.0 * scroll;

    vec3 gcol = vec3(0.0);

    float dr = abs(pp.x) - off;

    vec2 mp = pp;
    mod2(mp, vec2(off * 0.5));

    vec2 dp = abs(mp);
    float d = dp.x;
    d = pmin(d, dp.y, sm);
    d = max(d, -dr);
    vec2 s2 = sin(time + 2.0 * p.xz / off);
    float m = mix(0.75, 0.9, tanh_approx(s2.x + s2.y));
    m *= m;
    m *= m;
    m *= m;
    vec3 hsv = vec3(0.4 + mix(0.5, 0.0, m), tanh_approx(0.15 * mix(30.0, 10.0, m) * d), 1.0);
    float fo = exp(-0.04 * max(abs(t) - off * 2.0, 0.0));
    float foGrid = exp(-0.018 * max(abs(t) - off * 1.5, 0.0));
    vec3 neon = hsv2rgb(hsv);
    vec3 bcol = neonTheme(neon, u_color_secondary);
    gcol += 2.0 * bcol * exp(-0.1 * mix(30.0, 10.0, m) * d) * foGrid;

    float sh;
    float sdb;
    float sd = synth(opp, aa, sh, sdb) * smoothstep(aa, -aa, -dr);
    sh = tanh_approx(sh);
    sdb *= 0.055;
    sdb *= sdb;
    sdb += 0.035;
    vec3 eqCol = neonTheme(vec3(0.35, 0.7, 1.0), u_color_secondary);
    vec3 scol = sd * sdb * eqCol * (0.65 + 0.35 * sh);
    gcol += scol * fo;

    gcol = t > 0.0 ? gcol : vec3(0.0);
    return gcol;
}}

vec3 stars(vec2 sp, float hh) {{
    vec3 col = vec3(0.0);
    hh = tanh_approx(20.0 * hh);

    for (float i = 0.0; i < MAX_STAR_LAYERS; ++i) {{
        if (i >= u_star_layers) break;
        vec2 pp = sp + 0.5 * i;
        float s = i / max(u_star_layers - 1.0, 1.0);
        vec2 dim = vec2(mix(0.05, 0.003, s) * PI);
        vec2 np = mod2(pp, dim);
        vec2 hv = hash2(np + 127.0 + i);
        vec2 o = -1.0 + 2.0 * hv;
        float y = sin(sp.x);
        pp += o * dim * 0.5;
        pp.y *= y;
        float l = length(pp);

        float h1 = fract(hv.x * 1667.0);
        float h2 = fract(hv.x * 1887.0);
        float h3 = fract(hv.x * 2997.0);

        vec3 scol = mix(8.0 * h2, 0.25 * h2 * h2, s) * blackbody(mix(3000.0, 22000.0, h1 * h1));

        vec3 ccol = col + exp(-(mix(6000.0, 2000.0, hh) / mix(2.0, 0.25, s)) * max(l - 0.001, 0.0)) * scol;
        ccol *= mix(0.125, 1.0, smoothstep(1.0, 0.99, sin(0.25 * u_t * u_speed + TAU * hv.y)));
        col = h3 < y ? ccol : col;
    }}

    return col;
}}

vec3 meteorite(vec2 sp, float time) {{
    const float period = 3.0;
    float mtime = mod(time, period);
    float ntime = floor(time / period);
    float h0 = hash(ntime + 123.4);
    float h1 = fract(1667.0 * h0);
    float h2 = fract(9967.0 * h0);
    vec2 mp = sp;
    mp.x += -1.0;
    mp.y += -0.5 * h1;
    mp.y += PI * 0.5;
    mp *= ROT(PI + mix(-PI / 4.0, PI / 4.0, h0));
    float m = mtime / period;
    mp.x += mix(-1.0, 2.0, m);

    float d0 = length(mp);
    float d1 = segmentx(mp);

    vec3 col = vec3(0.0);

    col += 0.5 * exp(-4.0 * max(d0, 0.0)) * exp(-1000.0 * max(d1, 0.0));
    col *= 2.0 * themeTint(HSV2RGB(vec3(0.8, 0.5, 1.0)), u_color_accent);
    float fl = smoothstep(-0.5, 0.5, sin(12.0 * TAU * time));
    col += mix(1.0, 0.5, fl) * exp(-mix(100.0, 150.0, fl) * max(d0, 0.0)) * u_color_accent;

    col = h2 > 0.8 ? col : vec3(0.0);
    return col;
}}

vec3 skyGrid(vec2 sp) {{
    const vec2 dim = vec2(1.0 / 12.0 * PI);
    float y = sin(sp.x);
    vec2 pp = sp;
    vec2 np = mod2(pp, dim * vec2(1.0 / floor(1.0 / y), 1.0));

    vec3 col = vec3(0.0);

    float d = min(abs(pp.x), abs(pp.y * y));

    col += 0.25 * u_color_accent * exp(-2000.0 * max(d - 0.00025, 0.0));

    return col;
}}

vec3 sunset(vec2 sp, vec2 nsp) {{
    const float szoom = 0.5;
    float aa = length(nsp - sp) * sqrt(0.5);
    sp -= vec2(0.5, -0.5) * PI;
    sp /= szoom;
    sp = sp.yx;
    sp.y += 0.22;
    sp.y = -sp.y;
    float ds = sun(sp) * szoom;

    vec3 bscol = themeTint(hsv2rgb(vec3(fract(0.7 - 0.25 * sp.y), 1.0, 1.0)), u_color_primary);
    vec3 gscol = 0.75 * sqrt(bscol) * exp(-50.0 * max(ds, 0.0));
    vec3 scol = mix(gscol, bscol, smoothstep(aa, -aa, ds));
    return scol;
}}

vec3 glow(vec3 ro, vec3 rd, vec2 sp, vec3 lp, float beat) {{
    float ld = max(dot(normalize(lp - ro), rd), 0.0);
    float y = -0.5 + sp.x / PI;
    y = max(abs(y) - 0.02, 0.0) + 0.1 * smoothstep(0.5, PI, abs(sp.y));
    float ci = pow(ld, 10.0) * 2.0 * exp(-25.0 * y);
    ci *= 1.0 + beat * 0.5;
    float h = 0.65;
    vec3 col = themeTint(hsv2rgb(vec3(h, 0.75, 0.35 * exp(-15.0 * y))), u_color_primary);
    col += themeTint(HSV2RGB(vec3(0.8, 0.75, 0.5)), u_color_primary) * ci;
    return col;
}}

vec3 neonSky(vec3 ro, vec3 rd, vec3 nrd, float time, float star_drive, float high_boost, out float gl) {{
    const vec3 lp = 500.0 * vec3(0.0, 0.25, -1.0);
    vec3 skyCol = u_color_secondary * 0.08;

    float glare = pow(abs(dot(rd, normalize(lp))), 20.0);

    vec2 sp = toSpherical(rd.xzy).yz;
    vec2 nsp = toSpherical(nrd.xzy).yz;
    vec3 grd = rd;
    grd.xy *= ROT(0.025 * time);
    vec2 spp = toSpherical(grd).yz;

    float gm = 1.0 / abs(rd.y) * mix(0.005, 2.0, glare);
    if (rd.y < 0.0) {{
        // Stop the purple sky blow-up from erasing the horizon EQ + grid.
        gm = min(gm, 5.0);
    }}
    vec3 col = skyCol * gm;
    float ig = 1.0 - glare;
    ig *= 1.0 + high_boost;
    // Glow is sky-only; on a flat floor it reads as a bogus circular reflection.
    if (rd.y > 0.0) {{
        col += glow(ro, rd, sp, lp, u_beat_decay);
        col += sunset(sp, nsp);
        col += stars(sp, star_drive) * ig;
        col += skyGrid(spp) * ig;
        col += meteorite(sp, time) * ig;
    }}
    gl = glare;
    return col;
}}

vec3 colorScene(vec3 ro, vec3 rd, vec3 nrd, float time, float star_drive, float high_boost) {{
    // Original uses -off1 with off1 = -20 → plane.w = +20.
    const vec4 pl1 = vec4(normalize(vec3(0.0, 1.0, 0.15)), ROAD_OFF);
    float glare;
    vec3 col = neonSky(ro, rd, nrd, time, star_drive, high_boost, glare);
    if (rd.y < 0.0) {{
        float t_hit;
        col += road(ro, rd, nrd, glare, pl1, time, t_hit);
    }}
    return col;
}}

void main() {{
    float px = gl_FragCoord.x - u_origin.x;
    float py = (u_canvas_h - gl_FragCoord.y) - u_origin.y;

    if (px < 0.0 || px >= u_res.x || py < 0.0 || py >= u_res.y) discard;

    vec2 q = vec2(px, py) / u_res.xy;
    vec2 p = -1.0 + 2.0 * q;
    p.x *= u_res.x / u_res.y;
    // Shadertoy fragCoord is y-up; Pixfabrica py is y-down.
    p.y = -p.y;
    float aa = 2.0 / u_res.y;
    vec3 ro = vec3(0.0, 0.0, 10.0);
    vec3 la = vec3(0.0, 2.0, 0.0);
    vec3 up = vec3(0.0, 1.0, 0.0);

    vec3 ww = normalize(la - ro);
    vec3 uu = normalize(cross(up, ww));
    vec3 vv = normalize(cross(ww, uu));
    const float fov = tan(TAU / 6.0);
    vec2 np = p + vec2(aa);
    vec3 rd = normalize(-p.x * uu + p.y * vv + fov * ww);
    vec3 nrd = normalize(-np.x * uu + np.y * vv + fov * ww);

    float time = u_t * u_speed;
    float star_drive = u_mid * u_sensitivity;
    float high_boost = u_high * u_sensitivity * 0.5;

    vec3 col = colorScene(ro, rd, nrd, time, star_drive, high_boost);
    col *= 1.0 + u_amplitude * u_sensitivity * 0.25;
    col = aces_approx(col);
    col = sRGB(col);

    frag_color = vec4(col * u_opacity, u_opacity);
}}
"""

_QUAD = np.array(
    [-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0],
    dtype="f4",
)


def _shape_spectrum(spec: np.ndarray) -> np.ndarray:
    return np.clip(spec * spec * _SPECTRUM_GAIN, 0.0, 1.2).astype(np.float32)


def _demo_spectrum_raw(total_frames: int, fps: float) -> np.ndarray:
    t = np.arange(total_frames, dtype=np.float32) / max(fps, 1e-6)
    freq_x = np.arange(N_SPECTRUM, dtype=np.float32) / N_SPECTRUM
    wave = np.sin(t[:, None] * 4.0 + freq_x[None, :] * 10.0) * 0.5 + 0.5
    bass = np.sin(t[:, None] * 2.2) * 0.35 + 0.55
    return np.clip(wave * bass, 0.0, 1.0).astype(np.float32)


def _demo_spectrum_timeline(total_frames: int, fps: float) -> np.ndarray:
    return _shape_spectrum(_demo_spectrum_raw(total_frames, fps))


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


def _precompute_spectrum_timeline(
    *,
    total_frames: int,
    fps: float,
    sensitivity: float,
    bus_frames: list[AudioBusFrame] | None,
) -> np.ndarray:
    if total_frames <= 0:
        return np.zeros((0, N_SPECTRUM), dtype=np.float32)

    n_bus = len(bus_frames) if bus_frames else 0
    if n_bus > 0:
        assert bus_frames is not None
        normalized = _normalize_spectrum_timeline(bus_frames, n_bus)
        raw = np.zeros((total_frames, N_SPECTRUM), dtype=np.float32)
        n_copy = min(total_frames, n_bus)
        raw[:n_copy] = np.clip(normalized[:n_copy] * float(sensitivity), 0.0, 1.0)
        if n_copy < total_frames:
            raw[n_copy:] = _demo_spectrum_raw(total_frames - n_copy, fps)
        return _shape_spectrum(_smooth_spectrum_timeline(raw, _SPECTRUM_SMOOTHING))
    return _shape_spectrum(
        _smooth_spectrum_timeline(
            _demo_spectrum_raw(total_frames, fps),
            _SPECTRUM_SMOOTHING,
        )
    )


def _precompute_beat_decay(
    frames: list[AudioBusFrame] | None,
    total: int,
) -> np.ndarray:
    history = np.zeros(max(total, 0), dtype=np.float32)
    if total <= 0 or not frames:
        return history
    n_bus = min(total, len(frames))
    d = 0.0
    for f in range(total):
        if f < n_bus:
            d = 1.5 if frames[f].beat else d * 0.82
        else:
            d *= 0.82
        history[f] = d
    return history


class NeonSunsetGL(AudioVisualMixin, ClipGL):
    """Synthwave horizon — sunset disc, star field, infinite neon road, and spectrum-driven EQ."""

    clip_type: ClassVar[str] = "std-neon-sunset-gl"
    clip_category: ClassVar[ClipCategory] = ClipCategory.BACKGROUND
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED, ClipTag.GL, ClipTag.AUDIO_REACTIVE]

    color_primary: ColorToken | Color = color_field(ColorToken.PRIMARY)
    color_secondary: ColorToken | Color = color_field(ColorToken.SECONDARY)
    color_accent: ColorToken | Color = color_field(ColorToken.ACCENT)
    speed: float = Field(
        default=1.0,
        ge=0.1,
        le=3.0,
        multiple_of=0.1,
        description="Road scroll and sky motion speed multiplier",
    )
    star_layers: int = Field(
        default=5,
        ge=2,
        le=_MAX_STAR_LAYERS,
        multiple_of=1,
        description="Star field depth layers (2 = sparse, 5 = dense; preview caps lower)",
    )
    sensitivity: float = Field(
        default=2.5,
        ge=0.1,
        le=8.0,
        multiple_of=0.1,
        description="Audio response gain on spectrum and bus bands after job-wide normalization",
    )
    opacity: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Overall layer opacity",
    )

    _canvas_h: float = PrivateAttr(default=0.0)
    _bounds_x: float = PrivateAttr(default=0.0)
    _bounds_y: float = PrivateAttr(default=0.0)
    _bounds_w: float = PrivateAttr(default=0.0)
    _bounds_h: float = PrivateAttr(default=0.0)
    _for_preview: bool = PrivateAttr(default=False)

    _bass_history: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype="f4"))
    _mid_history: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype="f4"))
    _high_history: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype="f4"))
    _amp_history: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype="f4"))
    _beat_decay_frames: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype="f4"))
    _spectrum_history: np.ndarray = PrivateAttr(
        default_factory=lambda: np.zeros((0, N_SPECTRUM), dtype="f4")
    )

    _program: moderngl.Program | None = PrivateAttr(default=None)
    _vao: moderngl.VertexArray | None = PrivateAttr(default=None)
    _spectrum_tex: moderngl.Texture | None = PrivateAttr(default=None)
    _shader_revision: int = PrivateAttr(default=0)

    async def prepare(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        b = bounds or Rect(0, 0, ctx.job.width, ctx.job.height)
        self._canvas_h = float(ctx.job.height)
        self._bounds_x = float(b.x)
        self._bounds_y = float(b.y)
        self._bounds_w = float(b.width)
        self._bounds_h = float(b.height)
        self._for_preview = bool(ctx.for_preview)

        bus = self.bus_timeline(ctx)
        total = max(ctx.job.total_frames, 0)
        self._bass_history, self._mid_history, self._high_history, self._amp_history = (
            precompute_bus_drives(bus, total)
        )
        self._beat_decay_frames = _precompute_beat_decay(bus, total)
        self._spectrum_history = _precompute_spectrum_timeline(
            total_frames=total,
            fps=float(ctx.job.fps),
            sensitivity=float(self.sensitivity),
            bus_frames=bus,
        )
        self._spectrum_tex = None

    def _effective_star_layers(self) -> float:
        layers = int(self.star_layers)
        if self._for_preview:
            layers = min(layers, _PREVIEW_STAR_LAYERS_CAP)
        return float(layers)

    def _set_uniform(self, prog: moderngl.Program, name: str, value: Any) -> None:
        if name not in prog:
            return
        member = prog[name]
        if isinstance(member, moderngl.Uniform):
            member.value = value

    def _audio_drives_for_frame(
        self,
        ctx: RenderContext,
    ) -> tuple[float, float, float, float, float, bool]:
        if not self.bus_active_for_draw(ctx):
            return 0.0, 0.0, 0.0, 0.0, 0.0, True
        if self._bass_history.shape[0] > 0:
            f = max(0, min(ctx.time.frame, self._bass_history.shape[0] - 1))
            bass = min(1.0, float(self._bass_history[f]))
            mid = min(1.0, float(self._mid_history[f]))
            high = min(1.0, float(self._high_history[f]))
            amp = min(1.0, float(self._amp_history[f]))
            beat = (
                float(self._beat_decay_frames[f]) if self._beat_decay_frames.shape[0] > 0 else 0.0
            )
            return bass, mid, high, amp, beat, True
        af = ctx.audio_bus_frame
        return (
            self.scale_audio(float(af.bass)),
            self.scale_audio(float(af.mid)),
            self.scale_audio(float(af.high)),
            self.scale_audio(float(af.amplitude)),
            1.5 if af.beat else 0.0,
            False,
        )

    def _spectrum_for_frame(self, ctx: RenderContext) -> np.ndarray:
        if self._spectrum_history.shape[0] > 0:
            f = max(0, min(ctx.time.frame, self._spectrum_history.shape[0] - 1))
            return self._spectrum_history[f]
        if self.bus_active_for_draw(ctx):
            spec = np.clip(
                np.asarray(ctx.audio_bus_frame.spectrum, dtype=np.float32)
                * float(self.sensitivity),
                0.0,
                1.0,
            )
            return _shape_spectrum(spec)
        return _demo_spectrum_timeline(1, float(ctx.job.fps))[0]

    def _ensure_program(self, gl: moderngl.Context) -> None:
        if self._program is not None and self._shader_revision == _SHADER_REVISION:
            return
        self._program = gl.program(vertex_shader=_VERT, fragment_shader=_FRAG)
        vbo = gl.buffer(_QUAD.tobytes())
        self._vao = gl.simple_vertex_array(self._program, vbo, "in_vert")
        self._shader_revision = _SHADER_REVISION
        self._spectrum_tex = None

    def _ensure_spectrum_texture(self, gl: moderngl.Context, row: np.ndarray) -> None:
        data = np.ascontiguousarray(row, dtype=np.float32)
        if self._spectrum_tex is None:
            self._spectrum_tex = gl.texture((N_SPECTRUM, 1), 1, dtype="f4")
            self._spectrum_tex.filter = (moderngl.NEAREST, moderngl.NEAREST)
            self._spectrum_tex.repeat_x = True
            self._spectrum_tex.repeat_y = False
        self._spectrum_tex.write(data.tobytes())

    def draw(self, ctx: RenderContext) -> None:
        gl: moderngl.Context = ctx.canvas

        self._ensure_program(gl)

        prog = self._program
        assert prog is not None
        spectrum_row = self._spectrum_for_frame(ctx)
        self._ensure_spectrum_texture(gl, spectrum_row)
        assert self._spectrum_tex is not None
        self._spectrum_tex.use(0)

        bass, mid, high, amp, beat_decay, shader_sens = self._audio_drives_for_frame(ctx)

        self._set_uniform(prog, "u_res", (self._bounds_w, self._bounds_h))
        self._set_uniform(prog, "u_origin", (self._bounds_x, self._bounds_y))
        self._set_uniform(prog, "u_canvas_h", self._canvas_h)
        self._set_uniform(prog, "u_t", float(ctx.time.t))
        self._set_uniform(prog, "u_speed", float(self.speed))
        self._set_uniform(prog, "u_star_layers", self._effective_star_layers())
        self._set_uniform(
            prog,
            "u_sensitivity",
            float(self.sensitivity) if shader_sens else 1.0,
        )
        self._set_uniform(prog, "u_opacity", float(self.opacity))
        self._set_uniform(prog, "u_spectrum", 0)

        r1, g1, b1, _ = resolve_color(self.color_primary, ctx.job.colors).rgba
        r2, g2, b2, _ = resolve_color(self.color_secondary, ctx.job.colors).rgba
        r3, g3, b3, _ = resolve_color(self.color_accent, ctx.job.colors).rgba
        self._set_uniform(prog, "u_color_primary", (r1, g1, b1))
        self._set_uniform(prog, "u_color_secondary", (r2, g2, b2))
        self._set_uniform(prog, "u_color_accent", (r3, g3, b3))

        self._set_uniform(prog, "u_bass", bass)
        self._set_uniform(prog, "u_mid", mid)
        self._set_uniform(prog, "u_high", high)
        self._set_uniform(prog, "u_amplitude", amp)
        self._set_uniform(prog, "u_beat_decay", beat_decay)

        gl.scissor = (
            int(self._bounds_x),
            int(ctx.job.height - self._bounds_y - self._bounds_h),
            int(self._bounds_w),
            int(self._bounds_h),
        )

        assert self._vao is not None
        self._vao.render(moderngl.TRIANGLES)

        gl.scissor = None
