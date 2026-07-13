from __future__ import annotations

from typing import Any, ClassVar, cast

import moderngl
import numpy as np
from pydantic import Field, PrivateAttr

from pixfabrica_core.audio.bus import AudioBusFrame
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
uniform float u_speed;
uniform vec3  u_color_primary;
uniform vec3  u_color_secondary;
uniform float u_brightness_primary;
uniform float u_brightness_secondary;
uniform float u_tube_radius;
uniform float u_opacity;

out vec4 frag_color;

vec3 tunnel_path(float z) {
    return vec3(
        cos(z * 0.015) * 16.0 + cos(z * 0.006) * 64.0,
        cos(z * 0.011) * 24.0 + cos(z * 0.009) * 32.0,
        z
    );
}

mat2 cam_rot(float a) {
    vec4 v = cos(a + vec4(0.0, 33.0, 11.0, 0.0));
    return mat2(v.x, v.y, v.z, v.w);
}

float boxen(vec3 p) {
    p = abs(fract(p / 40.0) * 40.0 - 20.0) - 2.0;
    return min(p.x, min(p.y, p.z));
}

vec4 g_lights;

float map(vec3 p) {
    vec3 q = tunnel_path(p.z);
    float m, g = q.y - p.y + 6.0;

    m = boxen(p);
    p.xy -= q.xy;

    float red  = length(p.xy - sin(p.y / 12.0 + vec2(5.0, 1.0)) * 12.0) - u_tube_radius;
    float blue = length(p.xy - sin(p.y / 12.0 + vec2(0.0, 1.0)) * 12.0) - u_tube_radius;
    float e = min(red, blue);

    // g_lights deliberately accumulates across all map() calls within a pass —
    // tubes encountered early in the march continue contributing to later steps,
    // which creates the bloom/glow history seen in the original shader.
    g_lights += vec4(u_color_primary  * 8.0, 0.0) * u_brightness_primary  / (0.1 + abs(red)  / 10.0);
    g_lights += vec4(u_color_secondary * 8.0, 0.0) * u_brightness_secondary / (0.1 + abs(blue) / 10.0);

    p = abs(p);
    // Camera starts at exactly tunnel_path(T), so p.xy == 0 on the first ray step
    // every frame — sin(0)/0 = NaN. Clamp to avoid NaN propagation on strict drivers.
    vec3 pc = max(p, vec3(1e-6));
    float tex = abs(length(sin(pc * cos(pc.yzx / 30.0) * 4.0) / (pc * 4.0)));
    float tun = min(64.0 - p.x - p.y + m, 32.0 - p.y - m);

    float d = max(min(m, g), tun) - tex;
    return min(e, d);
}

void main() {
    float px = gl_FragCoord.x - u_origin.x;
    float py = (u_canvas_h - gl_FragCoord.y) - u_origin.y;

    vec2 uv = (vec2(px, py) - u_res * 0.5) / u_res.y;
    uv.y -= 0.2;

    float speed_t = u_t * u_speed;
    float T = sin(speed_t * 0.6) * 64.0 + speed_t * 200.0;

    g_lights = vec4(0.0);
    float i = 0.0, s = 0.0, d = 0.0;
    vec4 o = vec4(0.0);

    vec3 cam = tunnel_path(T);
    vec3 ro   = cam;
    vec3 Z    = normalize(tunnel_path(T + 10.0) - cam);
    vec3 X    = normalize(vec3(Z.z, 0.0, -Z.x));
    vec3 D    = normalize(vec3(cam_rot(sin(T * 0.005) * 0.4) * uv, 1.0) * mat3(-X, cross(X, Z), Z));

    vec3 p;
    for (; i++ < 64.0;) {
        p  = ro + D * d;
        s  = map(p) * 0.8;
        d += s;
        o += g_lights + 1.0 / max(s, 0.01);
    }

    // tetrahedron normal — https://iquilezles.org/articles/normalsSDF/
    const float h = 0.005;
    const vec2 k = vec2(1.0, -1.0);
    vec3 n = normalize(
        k.xyy * map(p + k.xyy * h) +
        k.yyx * map(p + k.yyx * h) +
        k.yxy * map(p + k.yxy * h) +
        k.xxx * map(p + k.xxx * h)
    );

    o *= (0.1 + max(dot(n, -D), 0.0));

    // reflection march
    vec4 ref = vec4(0.0);
    g_lights = vec4(0.0);
    p += n * 0.05;
    D  = reflect(D, n);
    i = 0.0; s = 0.0;
    for (; i++ < 32.0;) {
        p += D * s;
        s  = map(p) * 0.8;
        ref += g_lights + 1.0 / max(s, 0.01);
    }

    o += o * ref;
    o = tanh(o / 6e6 / max(d, 1e-5));

    // Dark raymarch regions stay transparent so lower tracks (and mesh opacity) show through.
    float luma = max(o.r, max(o.g, o.b));
    float a = smoothstep(0.12, 0.35, luma) * u_opacity;
    frag_color = vec4(o.rgb * a, a);
}
"""

_QUAD = np.array(
    [-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0],
    dtype="f4",
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


class NeonTunnelGL(AudioVisualMixin, ClipGL):
    """Raymarched neon tunnel — camera flies a sinusoidal path through a repeating
    box-lattice lit by two theme-colored tubes, with reflections and audio-reactive glow."""

    clip_type: ClassVar[str] = "std-neon-tunnel-gl"
    clip_category: ClassVar[ClipCategory] = ClipCategory.BACKGROUND
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED, ClipTag.GL, ClipTag.AUDIO_REACTIVE]

    color_primary: ColorToken | Color = color_field(ColorToken.PRIMARY)
    color_secondary: ColorToken | Color = color_field(ColorToken.SECONDARY)
    speed: float = Field(
        default=1.0, ge=0.1, le=3.0, multiple_of=0.1, description="Camera travel speed multiplier"
    )
    opacity: float = Field(
        default=1.0, ge=0.0, le=1.0, multiple_of=0.1, description="Overall layer opacity"
    )
    sensitivity: float = Field(
        default=2.5,
        ge=0.1,
        le=8.0,
        multiple_of=0.1,
        description="Audio response gain on bass/high tube glow after job-wide normalization",
    )

    _canvas_h: float = PrivateAttr(default=0.0)
    _bounds_x: float = PrivateAttr(default=0.0)
    _bounds_y: float = PrivateAttr(default=0.0)
    _bounds_w: float = PrivateAttr(default=0.0)
    _bounds_h: float = PrivateAttr(default=0.0)

    _bass_history: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype="f4"))
    _high_history: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype="f4"))
    _beat_decay_frames: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype="f4"))
    _program: moderngl.Program | None = PrivateAttr(default=None)
    _vao: moderngl.VertexArray | None = PrivateAttr(default=None)

    async def prepare(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        b = bounds or Rect(0, 0, ctx.job.width, ctx.job.height)
        self._canvas_h = float(ctx.job.height)
        self._bounds_x = float(b.x)
        self._bounds_y = float(b.y)
        self._bounds_w = float(b.width)
        self._bounds_h = float(b.height)

        bus = self.bus_timeline(ctx)
        total = max(ctx.job.total_frames, 0)
        self._bass_history, _, self._high_history, _ = precompute_bus_drives(bus, total)
        self._beat_decay_frames = _precompute_beat_decay(bus, total)

    def _set_uniform(self, prog: moderngl.Program, name: str, value: Any) -> None:
        cast(moderngl.Uniform, prog[name]).value = value

    def _audio_drives_for_frame(
        self,
        ctx: RenderContext,
    ) -> tuple[float, float, float]:
        if not self.bus_active_for_draw(ctx):
            return 0.0, 0.0, 0.0
        sens = float(self.sensitivity)
        if self._bass_history.shape[0] > 0:
            f = max(0, min(ctx.time.frame, self._bass_history.shape[0] - 1))
            bass = min(1.0, float(self._bass_history[f]) * sens)
            high = min(1.0, float(self._high_history[f]) * sens)
            beat_flash = (
                float(self._beat_decay_frames[f]) if self._beat_decay_frames.shape[0] > 0 else 0.0
            )
        else:
            af = ctx.audio_bus_frame
            bass = self.scale_audio(float(af.bass))
            high = self.scale_audio(float(af.high))
            beat_flash = 1.5 if af.beat else 0.0
        return bass, high, beat_flash

    def draw(self, ctx: RenderContext) -> None:
        gl: moderngl.Context = ctx.canvas

        if self._program is None:
            self._program = gl.program(vertex_shader=_VERT, fragment_shader=_FRAG)
            vbo = gl.buffer(_QUAD.tobytes())
            self._vao = gl.simple_vertex_array(self._program, vbo, "in_vert")

        prog = self._program

        self._set_uniform(prog, "u_res", (self._bounds_w, self._bounds_h))
        self._set_uniform(prog, "u_origin", (self._bounds_x, self._bounds_y))
        self._set_uniform(prog, "u_canvas_h", self._canvas_h)
        self._set_uniform(prog, "u_t", ctx.time.t)
        self._set_uniform(prog, "u_speed", self.speed)

        r1, g1, b1, _ = resolve_color(self.color_primary, ctx.job.colors).rgba
        r2, g2, b2, _ = resolve_color(self.color_secondary, ctx.job.colors).rgba
        self._set_uniform(prog, "u_color_primary", (r1, g1, b1))
        self._set_uniform(prog, "u_color_secondary", (r2, g2, b2))

        bass, high, beat_flash = self._audio_drives_for_frame(ctx)
        self._set_uniform(prog, "u_brightness_primary", 1.0 + bass * 3.0 + beat_flash)
        self._set_uniform(prog, "u_brightness_secondary", 1.0 + high * 3.0 + beat_flash)
        self._set_uniform(prog, "u_tube_radius", 1.0 + bass * 0.6)
        self._set_uniform(prog, "u_opacity", self.opacity)

        gl.scissor = (
            int(self._bounds_x),
            int(ctx.job.height - self._bounds_y - ctx.bounds.height),
            int(self._bounds_w),
            int(self._bounds_h),
        )

        assert self._vao is not None
        self._vao.render(moderngl.TRIANGLES)

        gl.scissor = None
