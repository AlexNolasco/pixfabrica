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
from pixfabrica_core.clips import ClipCategory, ClipGL, ClipTag, PrepareContext, RenderContext
from pixfabrica_core.graphics import Rect
from pixfabrica_core.media_upload import MEDIA_UPLOAD_LIMITS
from pixfabrica_core.prepare_diagnostics import record_prepare_asset_failure
from pixfabrica_core.theme.color import Color, ColorToken, color_field, resolve_color
from pixfabrica_std.media_source import resolve_source_sync
from pixfabrica_std.mesh.shader_helper import precompute_bus_drives

log = logging.getLogger("pixfabrica.std.warped_grid")

_DEFAULT_TEXTURE_NAME = "warped_grid_default.png"
_ALLOWED_EXT = frozenset({".png", ".jpg", ".jpeg", ".webp"})
_MAX_BYTES = MEDIA_UPLOAD_LIMITS["image"]
_MIN_DIM = 128
_MAX_DIM = 2048
_MIN_ASPECT = 0.25
_MAX_ASPECT = 4.0
_SPEC_WIDTH = 1024

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
uniform float u_height_scale;
uniform float u_glow_pulse;
uniform float u_opacity;
uniform vec3  u_color_primary;
uniform vec3  u_color_secondary;
uniform sampler2D u_height_color;

out vec4 frag_color;

#define MARCH_STEPS 56
#define FAR 20.0

float objID;
vec2 gP;
vec3 gID;
vec4 gGlow;

mat2 rot2(float a) {
    float c = cos(a), s = sin(a);
    return mat2(c, -s, s, c);
}

float hash21(vec2 p) {
    return fract(sin(dot(p, vec2(27.609, 57.583))) * 43758.5453);
}

float hash31(vec3 p) {
    return fract(sin(dot(p, vec3(12.989, 78.233, 57.263))) * 43758.5453);
}

vec2 path(float z) {
    return vec2(3.0 * sin(z * 0.1) + 0.5 * cos(z * 0.4), 0.0);
}

vec3 getTex(vec2 p) {
    vec3 tx = texture(u_height_color, p / 8.0).xyz;
    return tx * tx;
}

float hm(vec2 p) {
    return dot(getTex(p), vec3(0.299, 0.587, 0.114));
}

float opExtrusion(float sdf, float pz, float h, float sf) {
    vec2 w = vec2(sdf, abs(pz) - h) + sf;
    return min(max(w.x, w.y), 0.0) + length(max(w, 0.0)) - sf;
}

float sBoxS(vec2 p, vec2 b, float sf) {
    p = abs(p) - b + sf;
    return length(max(p, 0.0)) + min(max(p.x, p.y), 0.0) - sf;
}

vec2 skewXY(vec2 p, vec2 s) {
    return mat2(1.0, -s.y, -s.x, 1.0) * p;
}

vec2 unskewXY(vec2 p, vec2 s) {
    return inverse(mat2(1.0, -s.y, -s.x, 1.0)) * p;
}

vec4 blocks(vec3 q) {
    const vec2 scale = vec2(1.0 / 5.0);
    const vec2 dim = scale;
    const vec2 s = dim * 2.0;
    const vec2 sk = vec2(-0.5, 0.5);
    float hs = 0.4 * u_height_scale;

    float d = 1e5;
    vec2 id = vec2(0.0);
    float height = 0.0;
    gP = vec2(0.0);

    const vec2 ps4[4] = vec2[4](
        vec2(-0.5, 0.5),
        vec2(0.5, 0.5),
        vec2(0.5, -0.5),
        vec2(-0.5, -0.5)
    );

    for (int i = 0; i < 4; i++) {
        vec2 cntr = ps4[i] * 0.5 - ps4[0] * 0.5;

        vec2 p = skewXY(q.xz, sk);
        vec2 ip = floor(p / s - cntr) + 0.5;
        p -= (ip + cntr) * s;
        p = unskewXY(p, sk);

        vec2 idi = ip + cntr;
        idi = unskewXY(idi * s, sk);

        vec2 idi1 = idi;
        float h1 = hm(idi1) * hs;
        float face1 = sBoxS(p, 2.0 / 5.0 * dim - 0.02 * scale.x, 0.015);
        float face1Ext = opExtrusion(face1, q.y + h1, h1, 0.006);

        vec2 offs = unskewXY(dim * 0.5, sk);
        vec2 idi2 = idi + offs;
        float h2 = hm(idi2) * hs;
        float face2 = sBoxS(p - offs, 1.0 / 5.0 * dim - 0.02 * scale.x, 0.015);
        float face2Ext = opExtrusion(face2, q.y + h2, h2, 0.006);

        vec4 di = face1Ext < face2Ext
            ? vec4(face1Ext, idi1, h1)
            : vec4(face2Ext, idi2, h2);

        if (di.x < d) {
            d = di.x;
            id = di.yz;
            height = di.w;
            gP = p;
        }
    }

    return vec4(d, id, height);
}

float getTwist(float z) {
    return z * 0.08;
}

float mapScene(vec3 p) {
    p.xy -= path(p.z);
    p.xy *= rot2(getTwist(p.z));
    p.y = abs(p.y) - 1.25;

    float fl = -p.y + 0.01;

    vec4 d4 = blocks(p);
    gID = d4.yzw;

    float rnd = hash21(gID.xy);
    gGlow.w = smoothstep(0.992, 0.997, sin(rnd * 6.2831 + u_t * u_speed * 0.25) * 0.5 + 0.5);
    gGlow.w *= u_glow_pulse;

    objID = fl < d4.x ? 1.0 : 0.0;
    return min(fl, d4.x);
}

float trace(vec3 ro, vec3 rd) {
    float t = hash31(ro.zxy + rd.yzx) * 0.25;
    gGlow = vec4(0.0);

    for (int i = 0; i < MARCH_STEPS; i++) {
        float d = mapScene(ro + rd * t);

        float ad = abs(d + (hash31(ro + rd) - 0.5) * 0.05);
        const float dst = 0.25;
        if (ad < dst) {
            gGlow.xyz += gGlow.w * (dst - ad) * (dst - ad) / (1.0 + t);
        }

        if (abs(d) < 0.001 * (1.0 + t * 0.05) || t > FAR) {
            break;
        }
        t += float(i) < 32 ? d * 0.4 : d * 0.7;
    }

    return min(t, FAR);
}

vec3 getNormal(vec3 p) {
    const float h = 0.001;
    const vec2 k = vec2(1.0, -1.0);
    return normalize(
        k.xyy * mapScene(p + k.xyy * h) +
        k.yyx * mapScene(p + k.yyx * h) +
        k.yxy * mapScene(p + k.yxy * h) +
        k.xxx * mapScene(p + k.xxx * h)
    );
}

void main() {
    float px = gl_FragCoord.x - u_origin.x;
    float py = (u_canvas_h - gl_FragCoord.y) - u_origin.y;

    if (px < 0.0 || px >= u_res.x || py < 0.0 || py >= u_res.y) {
        discard;
    }

    vec2 uv = (vec2(px, py) - u_res * 0.5) / u_res.y;

    float travel_t = u_t * u_speed;
    vec3 ro = vec3(0.0, 0.0, travel_t * 1.5);
    ro.xy += path(ro.z);

    vec3 lk = vec3(0.0, 0.0, ro.z + 0.25);
    lk.xy += path(lk.z);
    vec2 lkTwist = vec2(0.0, -0.1);
    lkTwist *= rot2(-getTwist(lk.z));
    lk.xy += lkTwist;

    vec3 lp = vec3(0.0, 0.0, ro.z + 3.0);
    lp.xy += path(lp.z);
    vec2 lpTwist = vec2(0.0, -0.3);
    lpTwist *= rot2(-getTwist(lp.z));
    lp.xy += lpTwist;

    float FOV = 1.0;
    float a = getTwist(ro.z);
    a += (path(ro.z).x - path(lk.z).x) / (ro.z - lk.z) / 4.0;
    vec3 fw = normalize(lk - ro);
    vec3 up = vec3(sin(a), cos(a), 0.0);
    vec3 cu = normalize(cross(up, fw));
    vec3 cv = cross(fw, cu);
    vec3 rd = normalize(uv.x * cu + uv.y * cv + fw / FOV);

    float t = trace(ro, rd);

    vec3 svGID = gID;
    float svObjID = objID;
    vec2 svP = gP;
    vec3 svGlow = gGlow.xyz;

    vec3 col = vec3(0.0);

    if (t < FAR) {
        vec3 sp = ro + rd * t;
        vec3 sn = getNormal(sp);

        vec3 texCol;
        vec3 txP = sp;
        txP.xy -= path(txP.z);
        txP.xy *= rot2(getTwist(txP.z));

        if (svObjID < 0.5) {
            vec3 tx = getTex(svGID.xy);
            float lum = dot(tx, vec3(0.299, 0.587, 0.114));
            float shade = smoothstep(0.08, 0.92, lum);
            texCol = mix(u_color_primary * 0.45, u_color_secondary, shade);
            texCol *= 0.65 + shade * 0.85;

            const float lvls = 8.0;
            float yDist = 1.25 + abs(txP.y) + svGID.z * 2.0;
            float hLn = abs(mod(yDist + 0.5 / lvls, 1.0 / lvls) - 0.5 / lvls);
            float hLn2 = abs(mod(yDist + 0.5 / lvls - 0.008, 1.0 / lvls) - 0.5 / lvls);
            if (yDist - 2.5 < 0.25 / lvls) hLn = 1e5;
            if (yDist - 2.5 < 0.25 / lvls) hLn2 = 1e5;
            texCol = mix(texCol, texCol * 2.0, 1.0 - smoothstep(0.0, 0.003, hLn2 - 0.0035));
            texCol = mix(texCol, texCol / 2.5, 1.0 - smoothstep(0.0, 0.003, hLn - 0.0035));

            float fDot = length(txP.xz - svGID.xy) - 0.0086;
            texCol = mix(texCol, texCol * 2.0, 1.0 - smoothstep(0.0, 0.005, fDot - 0.0035));
            texCol = mix(texCol, vec3(0.0), 1.0 - smoothstep(0.0, 0.005, fDot));
        } else {
            texCol = u_color_primary * 0.04;
        }

        vec3 ld = lp - sp;
        float lDist = max(length(ld), 0.001);
        ld /= lDist;

        float atten = 3.0 / (1.0 + lDist * lDist * 0.5);
        float diff = max(dot(sn, ld), 0.0);
        diff *= diff * 1.35;
        float spec = pow(max(dot(reflect(ld, sn), rd), 0.0), 32.0);
        float fre = pow(clamp(1.0 - abs(dot(sn, rd)) * 0.5, 0.0, 1.0), 4.0);

        vec3 freCol = mix(u_color_primary, u_color_secondary, 0.65);
        col = texCol * (diff + 0.2 + freCol * fre * 0.35 + freCol * spec * 3.0);
        col *= atten;
    }

    vec3 glowA = u_color_primary * 3.5;
    vec3 glowB = u_color_secondary * 3.5;
    svGlow *= mix(glowA, glowB, min(svGlow * 3.5, 1.25));
    col *= 0.25 + svGlow * 8.0;

    vec3 fog = mix(glowA, glowB, rd.y * 0.5 + 0.5);
    col = mix(col, fog / 1.35, smoothstep(0.0, 0.99, t * t / FAR / FAR));

    col = sqrt(max(col, 0.0));

    float luma = dot(col, vec3(0.299, 0.587, 0.114));
    float alpha = smoothstep(0.02, 0.12, luma) * u_opacity;
    frag_color = vec4(col * alpha, alpha);
}
"""

_QUAD = np.array(
    [-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0],
    dtype="f4",
)


def _procedural_grunge_rgb(size: int = 512) -> np.ndarray:
    """Tile-friendly hash noise when the bundled PNG is not present yet."""
    ys, xs = np.mgrid[0:size, 0:size].astype(np.float32)
    p = np.stack([xs, ys], axis=-1)
    h = np.sin(p[..., 0] * 0.071 + p[..., 1] * 0.113) * 43758.5453
    h += np.sin(p[..., 0] * 0.017 + p[..., 1] * 0.037 + 12.9898) * 127.1
    v = (_frac(np.sin(h) * 43758.5453) * 0.65 + 0.2).astype(np.float32)
    rgb = np.stack([v, v, v], axis=-1)
    return np.clip(rgb * 255.0, 0, 255).astype(np.uint8)


def _frac(x: np.ndarray) -> np.ndarray:
    return x - np.floor(x)


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
        log.warning("WarpedGridGL %s: could not resolve source %r — %s", clip_id, source, exc)
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
        log.warning("WarpedGridGL %s: failed to load image %r — %s", clip_id, local_path, exc)
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


def _build_spectrogram_rgb(
    bus: list[AudioBusFrame],
    width: int = _SPEC_WIDTH,
    *,
    sensitivity: float = 2.5,
) -> np.ndarray:
    n = len(bus)
    if n <= 0:
        return _procedural_grunge_rgb()

    xs = np.linspace(0, n - 1, width).astype(np.int64)
    grid = np.zeros((N_SPECTRUM, width), dtype=np.float32)
    for col, frame_idx in enumerate(xs):
        spec = bus[frame_idx].spectrum
        grid[:, col] = spec[:N_SPECTRUM]

    # Light vertical smoothing so spectrum rows read better as a height field.
    kernel = np.array([0.25, 0.5, 0.25], dtype=np.float32)
    padded = np.pad(grid, ((1, 1), (0, 0)), mode="edge")
    smoothed = kernel[0] * padded[:-2] + kernel[1] * padded[1:-1] + kernel[2] * padded[2:]

    lo, hi = np.percentile(smoothed, (5.0, 95.0))
    span = max(float(hi - lo), 1e-6)
    mag = np.clip((smoothed - lo) / span, 0.0, 1.0)
    mag = np.power(mag, 0.55)
    mag = np.clip(mag * float(sensitivity), 0.0, 1.0)
    rgb = mag[:, :, np.newaxis] * 255.0
    rgb = np.repeat(rgb, 3, axis=2)
    return np.clip(rgb, 0, 255).astype(np.uint8)


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
        log.debug("WarpedGridGL: bundled default unavailable (%s) — using procedural noise", exc)
    return _procedural_grunge_rgb()


def _resolve_heightmap_rgb(
    *,
    source: str | None,
    bus: list[AudioBusFrame] | None,
    ctx: PrepareContext,
    clip_id: str,
    clip_type: str,
    sensitivity: float,
) -> np.ndarray:
    if source and source.strip():
        user_rgb = _load_user_source_rgb(source.strip(), ctx, clip_id, clip_type)
        if user_rgb is not None:
            return user_rgb

    if bus:
        return _build_spectrogram_rgb(bus, sensitivity=sensitivity)

    return _load_bundled_rgb()


class WarpedGridGL(AudioVisualMixin, ClipGL):
    """Raymarched warped extruded grid — demoscene fly-through over a height-mapped
    pinwheel city. Height/color texture: optional image, else bus spectrogram, else bundled default."""

    clip_type: ClassVar[str] = "std-warped-grid-gl"
    clip_category: ClassVar[ClipCategory] = ClipCategory.BACKGROUND
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED, ClipTag.GL, ClipTag.AUDIO_REACTIVE]

    source: str | None = Field(
        default=None,
        description="Optional height/color map (local path or http(s) URL). Invalid images are ignored.",
    )
    color_primary: ColorToken | Color = color_field(ColorToken.PRIMARY)
    color_secondary: ColorToken | Color = color_field(ColorToken.SECONDARY)
    speed: float = Field(
        default=1.0, ge=0.1, le=3.0, multiple_of=0.1, description="Camera travel speed multiplier"
    )
    height_scale: float = Field(
        default=1.0,
        ge=0.0,
        le=2.0,
        multiple_of=0.1,
        description="Pylon extrusion strength (0 = flat, 1 = default, 2 = dramatic)",
    )
    opacity: float = Field(
        default=1.0, ge=0.0, le=1.0, multiple_of=0.1, description="Overall layer opacity"
    )
    sensitivity: float = Field(
        default=2.5,
        ge=0.1,
        le=8.0,
        multiple_of=0.1,
        description="Audio response gain on bus spectrogram height and glow pulse",
    )

    _canvas_h: float = PrivateAttr(default=0.0)
    _bounds_x: float = PrivateAttr(default=0.0)
    _bounds_y: float = PrivateAttr(default=0.0)
    _bounds_w: float = PrivateAttr(default=0.0)
    _bounds_h: float = PrivateAttr(default=0.0)

    _heightmap_rgb: np.ndarray | None = PrivateAttr(default=None)
    _amp_history: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype="f4"))
    _program: moderngl.Program | None = PrivateAttr(default=None)
    _vao: moderngl.VertexArray | None = PrivateAttr(default=None)
    _tex: moderngl.Texture | None = PrivateAttr(default=None)

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
        _, _, _, self._amp_history = precompute_bus_drives(bus, total)
        self._heightmap_rgb = _resolve_heightmap_rgb(
            source=self.source,
            bus=bus,
            ctx=ctx,
            clip_id=self.id,
            clip_type=self.clip_type,
            sensitivity=float(self.sensitivity),
        )
        self._tex = None

    def _glow_pulse_for_frame(self, ctx: RenderContext) -> float:
        if not self.bus_active_for_draw(ctx):
            return 1.0
        sens = float(self.sensitivity)
        if self._amp_history.shape[0] > 0:
            f = max(0, min(ctx.time.frame, self._amp_history.shape[0] - 1))
            amp = min(1.0, float(self._amp_history[f]) * sens)
        else:
            amp = self.scale_audio(float(ctx.audio_bus_frame.amplitude))
        pulse = 1.0 + amp * 0.35
        audio = self.audio(ctx)
        if audio.beat or audio.onset:
            return max(pulse, 2.5)
        if audio.percussion:
            return max(pulse, 1.6)
        return pulse

    def _ensure_texture(self, gl: moderngl.Context) -> None:
        if self._tex is not None or self._heightmap_rgb is None:
            return
        h, w, _ = self._heightmap_rgb.shape
        self._tex = gl.texture((w, h), 3, self._heightmap_rgb.tobytes())
        self._tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self._tex.repeat_x = True
        self._tex.repeat_y = True

    def _set_uniform(self, prog: moderngl.Program, name: str, value: Any) -> None:
        cast(moderngl.Uniform, prog[name]).value = value

    def draw(self, ctx: RenderContext) -> None:
        gl: moderngl.Context = ctx.canvas

        if self._program is None:
            self._program = gl.program(vertex_shader=_VERT, fragment_shader=_FRAG)
            vbo = gl.buffer(_QUAD.tobytes())
            self._vao = gl.simple_vertex_array(self._program, vbo, "in_vert")

        self._ensure_texture(gl)
        if self._tex is None:
            return

        prog = self._program
        glow_pulse = self._glow_pulse_for_frame(ctx)

        pr, pg, pb, _ = resolve_color(self.color_primary, ctx.job.colors).rgba
        sr, sg, sb, _ = resolve_color(self.color_secondary, ctx.job.colors).rgba

        self._set_uniform(prog, "u_res", (self._bounds_w, self._bounds_h))
        self._set_uniform(prog, "u_origin", (self._bounds_x, self._bounds_y))
        self._set_uniform(prog, "u_canvas_h", self._canvas_h)
        self._set_uniform(prog, "u_t", float(ctx.time.t))
        self._set_uniform(prog, "u_speed", float(self.speed))
        self._set_uniform(prog, "u_height_scale", float(self.height_scale))
        self._set_uniform(prog, "u_glow_pulse", float(glow_pulse))
        self._set_uniform(prog, "u_opacity", float(self.opacity))
        self._set_uniform(prog, "u_color_primary", (pr, pg, pb))
        self._set_uniform(prog, "u_color_secondary", (sr, sg, sb))

        self._tex.use(0)
        self._set_uniform(prog, "u_height_color", 0)

        gl.scissor = (
            int(self._bounds_x),
            int(ctx.job.height - self._bounds_y - ctx.bounds.height),
            int(self._bounds_w),
            int(self._bounds_h),
        )

        assert self._vao is not None
        self._vao.render(moderngl.TRIANGLES)

        gl.scissor = None
