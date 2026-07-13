from __future__ import annotations

from typing import Any, ClassVar

import moderngl
import numpy as np
from pydantic import Field, PrivateAttr

from pixfabrica_core.audio.mixin import AudioVisualMixin
from pixfabrica_core.clips import ClipCategory, ClipGL, ClipTag, PrepareContext, RenderContext
from pixfabrica_core.graphics import Rect
from pixfabrica_core.theme.color import Color, ColorToken, color_field, resolve_color
from pixfabrica_std.mesh.shader_helper import precompute_bus_drives

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

uniform float u_star_size;
uniform float u_star_count;
uniform float u_color_speed;
uniform float u_cam_height_min;
uniform float u_cam_height_max;
uniform float u_floor_reflect;
uniform float u_opacity;
uniform float u_bass_sensitivity;
uniform float u_beat_flash;
uniform vec3  u_cool_color;
uniform vec3  u_hot_color;

uniform float u_bass;
uniform float u_mid;
uniform float u_amplitude;
uniform float u_beat;

out vec4 frag_color;

// Global mutable state — written by main(), read by helpers
vec4 COOLCOLOR;
vec4 HOTCOLOR;
vec4 MIDCOLOR;
float time;

#define NUM_STARS   80
#define NUM_BOUNCES  6
#define NUM_ARCS     7
#define saturate(x) clamp(x, 0.0, 1.0)

const vec3  up    = vec3(0.0, 1.0, 0.0);
const float pi    = 3.141592653589793;

struct Ray {
    vec3 o;
    vec3 d;
};

struct Camera {
    vec3  p;
    vec3  forward;
    vec3  left;
    vec3  up;
    vec3  center;
    vec3  i;
    Ray   ray;
    vec3  lookAt;
    float zoom;
};
Camera cam;

void CameraSetup(vec2 uv, vec3 position, vec3 lookAt, float zoom) {
    cam.p       = position;
    cam.lookAt  = lookAt;
    cam.forward = normalize(cam.lookAt - cam.p);
    cam.left    = cross(up, cam.forward);
    cam.up      = cross(cam.forward, cam.left);
    cam.zoom    = zoom;
    cam.center  = cam.p + cam.forward * cam.zoom;
    cam.i       = cam.center + cam.left * uv.x + cam.up * uv.y;
    cam.ray.o   = cam.p;
    cam.ray.d   = normalize(cam.i - cam.p);
}

vec4 Noise4(vec4 x)    { return fract(sin(x) * 5346.1764) * 2.0 - 1.0; }
float Noise101(float x) { return fract(sin(x) * 5346.1764); }

float PeriodicPulse(float x, float p) {
    return pow((cos(x + sin(x)) + 1.0) / 2.0, p);
}

float DistSqr(vec3 a, vec3 b) { vec3 D = a - b; return dot(D, D); }

vec3 ClosestPoint(Ray r, vec3 p) {
    return r.o + max(0.0, dot(p - r.o, r.d)) * r.d;
}

float BounceNorm(float t, float decay) {
    float height = 1.0;
    float heights[NUM_ARCS];
    float halfDurations[NUM_ARCS];
    heights[0]       = 1.0;
    halfDurations[0] = 1.0;
    float halfDuration = 0.5;
    for (int i = 1; i < NUM_ARCS; i++) {
        height          *= decay;
        heights[i]       = height;
        halfDurations[i] = sqrt(height);
        halfDuration    += halfDurations[i];
    }
    t *= halfDuration * 2.0;

    float y = 1.0 - t * t;
    for (int i = 1; i < NUM_ARCS; i++) {
        t -= halfDurations[i-1] + halfDurations[i];
        y  = max(y, heights[i] - t * t);
    }
    return saturate(y);
}

vec4 SkyStar(Ray r, vec3 pos, float size_sky, vec4 col) {
    vec3 closestPoint = ClosestPoint(r, pos);
    float dist       = DistSqr(closestPoint, pos) / max(size_sky * size_sky, 1e-6);
    float brightness = 1.0 / max(dist, 1e-4);
    return col * brightness;
}

vec4 GroundStar(vec3 pos, float fade, vec3 I, vec3 R, float ground_flicker) {
    vec3  L    = pos - I;
    float dist = length(L);
    L         /= dist;

    float lambert = saturate(dot(L, up));
    float light   = lambert / max(dist, 0.001);
    vec4  col     = mix(COOLCOLOR, MIDCOLOR, fade);
    vec4  ground  = vec4(light) * 0.1 * col * ground_flicker;

    if (u_floor_reflect > 0.5) {
        float spec    = pow(saturate(dot(R, L)), 400.0);
        float fresnel = pow(1.0 - saturate(dot(L, up)), 10.0);
        vec4 specLight = col * spec / max(dist, 0.001);
        ground += specLight * fade * 0.5 * fresnel;
    }
    return ground;
}

// Stars() used seed Noise101(i+1); Ground() used Noise101(i). Iterate k so each
// seed is evaluated once: ground at k < star_count, sky at 1 <= k <= star_count.
vec4 SceneStars(Ray r) {
    vec4 sky    = vec4(0.0);
    vec4 ground = vec4(0.0);

    bool  do_ground      = r.d.y < 0.0;
    vec3  I              = vec3(0.0);
    vec3  R              = vec3(0.0);
    float ground_flicker = sin(time) * 0.5 + 0.6;
    if (do_ground) {
        float t_p = -r.o.y / r.d.y;
        I = r.o + max(0.0, t_p) * r.d;
        R = reflect(r.d, up);
    }

    int star_limit = int(u_star_count);
    for (int k = 0; k <= NUM_STARS; k++) {
        if (k > star_limit) break;

        bool for_ground = do_ground && k < star_limit;
        bool for_sky    = k >= 1 && k <= star_limit;
        if (!for_ground && !for_sky) continue;

        float seed = Noise101(float(k));
        vec4  nv   = Noise4(vec4(seed, seed + 1.0, seed + 2.0, seed + 3.0));

        float tStar    = fract(time * 0.1 + seed) * 2.0;
        float fade     = smoothstep(2.0, 0.5, tStar);
        float size_base = u_star_size * (1.0 + seed) * fade;
        float bounce   = BounceNorm(tStar, 0.4 + seed * 0.1) * 7.0;
        vec3  xz       = vec3(nv.x * 10.0, 0.0, nv.y * 10.0);

        if (for_ground) {
            vec3 pos_ground = xz + vec3(0.0, bounce + size_base, 0.0);
            ground += GroundStar(pos_ground, fade, I, R, ground_flicker);
        }
        if (for_sky) {
            float size_sky = size_base * (1.0 + u_bass * u_bass_sensitivity);
            vec3  pos_sky  = xz + vec3(0.0, bounce + size_sky, 0.0);
            sky += SkyStar(r, pos_sky, size_sky, mix(COOLCOLOR, HOTCOLOR, fade));
        }
    }
    return sky + ground;
}

void main() {
    // Convert gl_FragCoord to bottom-up bounds-local space (Shadertoy convention)
    float px = gl_FragCoord.x - u_origin.x;
    float py = gl_FragCoord.y - (u_canvas_h - u_origin.y - u_res.y);
    vec2 uv  = vec2(px, py) / u_res - 0.5;
    uv.y    *= u_res.y / u_res.x;

    // Time drives animation speed (star cycling, camera orbit, ground flicker)
    time = u_t * 0.4 * u_color_speed;

    float t = time * pi * 0.1;
    COOLCOLOR = vec4(u_cool_color, 1.0);
    HOTCOLOR  = vec4(u_hot_color,  1.0);

    // Beat flashes hot color toward white; sin pulse keeps it alive without audio
    float whiteFade = sin(time * 2.0) * 0.15 + 0.05;
    whiteFade = mix(whiteFade, 1.0, u_beat * u_beat_flash);
    HOTCOLOR  = mix(HOTCOLOR, vec4(1.0), whiteFade);
    MIDCOLOR  = (HOTCOLOR + COOLCOLOR) * 0.5;

    // Rotating camera orbit
    float s = sin(t);
    float c = cos(t);
    mat3 rot = mat3(c,   0.0, s,
                    0.0, 1.0, 0.0,
                    s,   0.0, -c);

    float camHeight = mix(u_cam_height_max, u_cam_height_min, PeriodicPulse(time * 0.1, 2.0));
    // Mid-frequency lifts the camera slightly
    camHeight *= 1.0 + u_mid * 0.3;

    vec3 pos = vec3(0.0, camHeight, -10.0) * rot * (1.0 + sin(time) * 0.3);
    CameraSetup(uv, pos, vec3(0.0), 0.5);

    vec4 col = SceneStars(cam.ray);

    // Amplitude drives overall brightness
    col.rgb *= 0.8 + u_amplitude * 0.4;

    // Premultiplied alpha output — treated as opaque background
    float a = u_opacity;
    frag_color = vec4(clamp(col.rgb, 0.0, 1.0) * a, a);
}
"""

_QUAD = np.array([-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0], dtype="f4")


class DyingUniverseGL(AudioVisualMixin, ClipGL):
    """Audio-reactive 3-D bouncing stars with a reflective floor.

    Ported from BigWings' "Dying Universe" Shadertoy shader.
    Stars bounce, fade, and color-cycle; bass swells star size; beats flash white.
    """

    clip_type: ClassVar[str] = "std-dying-universe-gl"
    clip_category: ClassVar[ClipCategory] = ClipCategory.PARTICLES
    clip_tags: ClassVar[list[str]] = [
        ClipTag.ANIMATED,
        ClipTag.LOOP,
        ClipTag.GL,
        ClipTag.AUDIO_REACTIVE,
    ]

    # Appearance
    cool_color: ColorToken | Color = color_field(ColorToken.SECONDARY)
    hot_color: ColorToken | Color = color_field(ColorToken.PRIMARY)
    star_size: float = Field(
        default=0.03,
        ge=0.005,
        le=0.15,
        multiple_of=0.01,
        description="Base star radius (world units)",
    )
    star_count: int = Field(
        default=80,
        ge=20,
        le=80,
        multiple_of=5,
        description="Number of bouncing stars (lower = faster render)",
    )
    speed: float = Field(
        default=1.0,
        ge=0.1,
        le=5.0,
        multiple_of=0.1,
        description="Animation speed multiplier (star cycling, camera orbit)",
    )
    cam_height_min: float = Field(
        default=0.1,
        ge=0.05,
        le=5.0,
        multiple_of=0.1,
        description="Minimum camera height (floor skim)",
    )
    cam_height_max: float = Field(
        default=3.5,
        ge=0.1,
        le=15.0,
        multiple_of=0.1,
        description="Maximum camera height (overhead view)",
    )
    floor_reflect: bool = Field(
        default=True,
        description="Enable specular floor reflections",
    )
    opacity: float = Field(default=1.0, ge=0.0, le=1.0, description="Overall layer opacity")

    # Audio
    bass_sensitivity: float = Field(
        default=0.5,
        ge=0.0,
        le=2.0,
        multiple_of=0.1,
        description="How much bass energy inflates star size (0 = off)",
    )
    beat_flash: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="White flash intensity on beat (0 = off)",
    )
    sensitivity: float = Field(
        default=2.5,
        ge=0.1,
        le=8.0,
        multiple_of=0.1,
        description="Audio response gain on bass/mid/amplitude after job-wide normalization",
    )

    # Private GL resources
    _program: moderngl.Program | None = PrivateAttr(default=None)
    _vao: moderngl.VertexArray | None = PrivateAttr(default=None)
    _canvas_h: float = PrivateAttr(default=0.0)
    _bounds_x: float = PrivateAttr(default=0.0)
    _bounds_y: float = PrivateAttr(default=0.0)
    _bounds_w: float = PrivateAttr(default=0.0)
    _bounds_h: float = PrivateAttr(default=0.0)
    _bass_history: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype="f4"))
    _mid_history: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype="f4"))
    _amp_history: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype="f4"))

    async def prepare(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        b = bounds or Rect(0, 0, ctx.job.width, ctx.job.height)
        self._canvas_h = float(ctx.job.height)
        self._bounds_x = float(b.x)
        self._bounds_y = float(b.y)
        self._bounds_w = float(b.width)
        self._bounds_h = float(b.height)
        total = max(ctx.job.total_frames, 0)
        self._bass_history, self._mid_history, _, self._amp_history = precompute_bus_drives(
            self.bus_timeline(ctx),
            total,
        )

    def _set_uniform(self, prog: moderngl.Program, name: str, value: Any) -> None:
        if name in prog:
            member = prog[name]
            if isinstance(member, moderngl.Uniform):
                member.value = value

    def _audio_drives_for_frame(self, ctx: RenderContext) -> tuple[float, float, float, float]:
        if not self.bus_active_for_draw(ctx):
            return 0.0, 0.0, 0.0, 0.0
        sens = float(self.sensitivity)
        if self._bass_history.shape[0] > 0:
            f = max(0, min(ctx.time.frame, self._bass_history.shape[0] - 1))
            bass = min(1.0, float(self._bass_history[f]) * sens)
            mid = min(1.0, float(self._mid_history[f]) * sens)
            amp = min(1.0, float(self._amp_history[f]) * sens)
        else:
            af = ctx.audio_bus_frame
            bass = self.scale_audio(float(af.bass))
            mid = self.scale_audio(float(af.mid))
            amp = self.scale_audio(float(af.amplitude))
        beat = 1.0 if self.audio(ctx).beat else 0.0
        return bass, mid, amp, beat

    def draw(self, ctx: RenderContext) -> None:
        gl: moderngl.Context = ctx.canvas

        if self._program is None:
            self._program = gl.program(vertex_shader=_VERT, fragment_shader=_FRAG)
            vbo = gl.buffer(_QUAD.tobytes())
            self._vao = gl.simple_vertex_array(self._program, vbo, "in_vert")

        prog = self._program
        bass, mid, amp, beat = self._audio_drives_for_frame(ctx)

        self._set_uniform(prog, "u_res", (self._bounds_w, self._bounds_h))
        self._set_uniform(prog, "u_origin", (self._bounds_x, self._bounds_y))
        self._set_uniform(prog, "u_canvas_h", self._canvas_h)
        self._set_uniform(prog, "u_t", ctx.time.t)

        self._set_uniform(prog, "u_star_size", self.star_size)
        self._set_uniform(prog, "u_star_count", float(self.star_count))
        self._set_uniform(prog, "u_color_speed", self.speed)
        self._set_uniform(prog, "u_cam_height_min", self.cam_height_min)
        self._set_uniform(prog, "u_cam_height_max", self.cam_height_max)
        self._set_uniform(prog, "u_floor_reflect", 1.0 if self.floor_reflect else 0.0)
        self._set_uniform(prog, "u_opacity", self.opacity)
        self._set_uniform(prog, "u_bass_sensitivity", self.bass_sensitivity)
        self._set_uniform(prog, "u_beat_flash", self.beat_flash)
        cr, cg, cb, _ = resolve_color(self.cool_color, ctx.job.colors).rgba
        hr, hg, hb, _ = resolve_color(self.hot_color, ctx.job.colors).rgba
        self._set_uniform(prog, "u_cool_color", (cr, cg, cb))
        self._set_uniform(prog, "u_hot_color", (hr, hg, hb))

        self._set_uniform(prog, "u_bass", bass)
        self._set_uniform(prog, "u_mid", mid)
        self._set_uniform(prog, "u_amplitude", amp)
        self._set_uniform(prog, "u_beat", beat)

        bnd = ctx.bounds
        gl.scissor = (
            int(self._bounds_x),
            int(self._canvas_h - self._bounds_y - bnd.height),
            int(self._bounds_w),
            int(bnd.height),
        )

        assert self._vao is not None
        self._vao.render(moderngl.TRIANGLES)
        gl.scissor = None
