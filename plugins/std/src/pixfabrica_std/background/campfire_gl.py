from __future__ import annotations

from typing import Any, ClassVar

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

# Adapted from an unnamed Shadertoy fire effect (simplex noise + sparks + smoke).
# Simplex noise: Ashima Arts / Ian McEwan — MIT License.
# PRNG: https://www.shadertoy.com/view/4djSRW
# Changes: removed iMouse; added audio uniforms, theme colors, flame_height param,
# luma-derived alpha.
_FRAG = """
#version 330 core

uniform vec2  u_res;
uniform vec2  u_origin;
uniform float u_canvas_h;
uniform float u_t;
uniform float u_speed;
uniform float u_flame_height;
uniform float u_smoke_amount;
uniform float u_sensitivity;
uniform float u_opacity;
uniform vec3  u_color_fire;
uniform vec3  u_color_sparks;
uniform float u_bass;
uniform float u_beat_decay;
uniform float u_amplitude;

out vec4 frag_color;

const float PI = 3.14159265358979;

// --- Ashima Arts 3D Simplex Noise ---
vec3 mod289v3(vec3 x) { return x - floor(x * (1.0/289.0)) * 289.0; }
vec4 mod289v4(vec4 x) { return x - floor(x * (1.0/289.0)) * 289.0; }
vec4 permute4(vec4 x)  { return mod289v4(((x*34.0)+1.0)*x); }

float snoise(vec3 v) {
    const vec2 C = vec2(1.0/6.0, 1.0/3.0);
    const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);

    vec3 i  = floor(v + dot(v, C.yyy));
    vec3 x0 = v - i + dot(i, C.xxx);

    vec3 g  = step(x0.yzx, x0.xyz);
    vec3 l  = 1.0 - g;
    vec3 i1 = min(g.xyz, l.zxy);
    vec3 i2 = max(g.xyz, l.zxy);

    vec3 x1 = x0 - i1 + C.xxx;
    vec3 x2 = x0 - i2 + C.yyy;
    vec3 x3 = x0 - D.yyy;

    i = mod289v3(i);
    vec4 p = permute4(permute4(permute4(
        i.z + vec4(0.0, i1.z, i2.z, 1.0))
      + i.y + vec4(0.0, i1.y, i2.y, 1.0))
      + i.x + vec4(0.0, i1.x, i2.x, 1.0));

    float n_  = 0.142857142857;
    vec3  ns  = n_ * D.wyz - D.xzx;

    vec4 j  = p - 49.0 * floor(p * ns.z * ns.z);
    vec4 x_ = floor(j * ns.z);
    vec4 y_ = floor(j - 7.0 * x_);
    vec4 x  = x_ * ns.x + ns.yyyy;
    vec4 y  = y_ * ns.x + ns.yyyy;
    vec4 h  = 1.0 - abs(x) - abs(y);

    vec4 b0 = vec4(x.xy, y.xy);
    vec4 b1 = vec4(x.zw, y.zw);

    vec4 s0 = floor(b0)*2.0 + 1.0;
    vec4 s1 = floor(b1)*2.0 + 1.0;
    vec4 sh = -step(h, vec4(0.0));

    vec4 a0 = b0.xzyw + s0.xzyw * sh.xxyy;
    vec4 a1 = b1.xzyw + s1.xzyw * sh.zzww;

    vec3 p0 = vec3(a0.xy, h.x);
    vec3 p1 = vec3(a0.zw, h.y);
    vec3 p2 = vec3(a1.xy, h.z);
    vec3 p3 = vec3(a1.zw, h.w);

    vec4 norm = inversesqrt(vec4(dot(p0,p0), dot(p1,p1), dot(p2,p2), dot(p3,p3)));
    p0 *= norm.x; p1 *= norm.y; p2 *= norm.z; p3 *= norm.w;

    vec4 m = max(0.6 - vec4(dot(x0,x0), dot(x1,x1), dot(x2,x2), dot(x3,x3)), 0.0);
    m = m * m;
    return 42.0 * dot(m*m, vec4(dot(p0,x0), dot(p1,x1), dot(p2,x2), dot(p3,x3)));
}

float prng(in vec2 seed) {
    seed  = fract(seed * vec2(5.3983, 5.4427));
    seed += dot(seed.yx, seed.xy + vec2(21.5351, 14.3137));
    return fract(seed.x * seed.y * 95.4337);
}

float noiseStack(vec3 pos, int octaves, float falloff) {
    float noise = snoise(pos);
    float off   = 1.0;
    if (octaves > 1) { pos *= 2.0; off *= falloff; noise = (1.0-off)*noise + off*snoise(pos); }
    if (octaves > 2) { pos *= 2.0; off *= falloff; noise = (1.0-off)*noise + off*snoise(pos); }
    if (octaves > 3) { pos *= 2.0; off *= falloff; noise = (1.0-off)*noise + off*snoise(pos); }
    return (1.0 + noise) * 0.5;
}

vec2 noiseStackUV(vec3 pos, int octaves, float falloff) {
    float a = noiseStack(pos, octaves, falloff);
    float b = noiseStack(pos + vec3(3984.293, 423.21, 5235.19), octaves, falloff);
    return vec2(a, b);
}

void main() {
    float px = gl_FragCoord.x - u_origin.x;
    float py = (u_canvas_h - gl_FragCoord.y) - u_origin.y;

    if (px < 0.0 || px >= u_res.x || py < 0.0 || py >= u_res.y) discard;

    // Remap to Shadertoy convention: frag_y = 0 at bottom, increases upward
    float frag_x = px;
    float frag_y = u_res.y - py;

    float realTime = u_t * u_speed * 0.5;

    // Flame height: bass kicks momentarily expand the reach of the flames
    float clip = clamp(u_flame_height * u_res.y * (1.0 + u_bass * u_sensitivity * 0.4),
                       1.0, u_res.y);

    float xpart = frag_x / u_res.x;
    float ypart = frag_y / u_res.y;

    float ypartClip           = frag_y / clip;
    float ypartClippedFalloff = clamp(2.0 - ypartClip, 0.0, 1.0);
    float ypartClipped        = min(ypartClip, 1.0);
    float ypartClippedn       = 1.0 - ypartClipped;

    // Horizontal fuel: maximum at center, zero at edges
    float xfuel = 1.0 - abs(2.0 * xpart - 1.0);

    vec2 coordScaled = 0.01 * vec2(frag_x, frag_y);
    vec3 position    = vec3(coordScaled, 0.0) + vec3(1223.0, 6434.0, 8425.0);
    vec3 flow        = vec3( 4.1*(0.5-xpart)*pow(ypartClippedn, 4.0),
                            -2.0*xfuel      *pow(ypartClippedn, 64.0),
                             0.0);
    vec3 timing      = realTime * vec3(0.0, -1.7, 1.1) + flow;

    vec3 displacePos = vec3(1.0,0.5,1.0)*2.4*position + realTime*vec3(0.01,-0.7,1.3);
    vec3 displace3   = vec3(noiseStackUV(displacePos, 2, 0.4), 0.0);

    vec3  noiseCoord = vec3(2.0,1.0,1.0)*position + timing + 0.4*displace3;
    float noise      = noiseStack(noiseCoord, 3, 0.4);

    float flames = pow(ypartClipped, 0.3*xfuel) * pow(noise, 0.3*xfuel);

    float f   = ypartClippedFalloff * pow(1.0 - flames*flames*flames, 8.0);
    float fff = f*f*f;
    // Primary color modulates the natural fire gradient (red > orange > yellow tip)
    // Bass pulses the intensity upward
    vec3 fire = 1.5 * u_color_fire * vec3(f, fff, fff*fff)
                * (1.0 + u_bass * u_sensitivity * 0.4);

    // Smoke — gray, scaled by smoke_amount param
    float smokeNoise = 0.5 + snoise(0.4*position + timing*vec3(1.0,1.0,0.2)) * 0.5;
    vec3  smoke      = u_smoke_amount
                     * vec3(0.3*pow(xfuel,3.0)*pow(ypart,2.0)
                            * (smokeNoise + 0.4*(1.0-noise)));

    // Sparks — beat decay bursts spark size on each detected beat
    float sparkGridSize  = 30.0;
    vec2  sparkCoord     = vec2(frag_x, frag_y) - vec2(0.0, 190.0*realTime);
    sparkCoord          -= 30.0 * noiseStackUV(0.01*vec3(sparkCoord, 30.0*u_t*u_speed), 1, 0.4);
    sparkCoord          += 100.0 * flow.xy;
    if (mod(sparkCoord.y / sparkGridSize, 2.0) < 1.0) sparkCoord.x += 0.5*sparkGridSize;

    vec2  sparkGridIndex = floor(sparkCoord / sparkGridSize);
    float sparkRandom    = prng(sparkGridIndex);
    float sparkLife      = min(10.0*(1.0 - min(
        (sparkGridIndex.y + (190.0*realTime/sparkGridSize)) / (24.0 - 20.0*sparkRandom),
        1.0)), 1.0);

    vec3 sparks = vec3(0.0);
    if (sparkLife > 0.0) {
        float sparkSize    = xfuel*xfuel*sparkRandom*0.08 * (1.0 + u_beat_decay * 1.5);
        float sparkRad     = 999.0*sparkRandom*2.0*PI + 2.0*u_t*u_speed;
        vec2  sparkCirc    = vec2(sin(sparkRad), cos(sparkRad));
        vec2  sparkOff     = (0.5 - sparkSize)*sparkGridSize*sparkCirc;
        vec2  sparkMod     = mod(sparkCoord+sparkOff, sparkGridSize) - 0.5*vec2(sparkGridSize);
        float sparksGray   = max(0.0, 1.0 - length(sparkMod)/(sparkSize*sparkGridSize));
        sparks = sparkLife * sparksGray * u_color_sparks;
    }

    vec3 col = max(fire, sparks) + smoke;
    // Amplitude lifts overall brightness — keeps the fire visible at quiet passages
    col *= 1.0 + u_amplitude * u_sensitivity * 0.3;

    // Luma-derived alpha: black void is transparent, bright fire/sparks opaque
    float luma  = dot(col, vec3(0.299, 0.587, 0.114));
    float alpha = smoothstep(0.05, 0.2, luma) * u_opacity;
    frag_color = vec4(col * alpha, alpha);
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


class CampfireGL(AudioVisualMixin, ClipGL):
    """Simplex-noise fire with rising sparks and smoke — three distinct visual layers,
    audio-reactive: bass swells flame height, beat bursts spark size, amplitude lifts
    overall brightness."""

    clip_type: ClassVar[str] = "std-campfire-gl"
    clip_category: ClassVar[ClipCategory] = ClipCategory.BACKGROUND
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED, ClipTag.GL, ClipTag.AUDIO_REACTIVE]

    color_fire: ColorToken | Color = color_field(ColorToken.PRIMARY)
    color_sparks: ColorToken | Color = color_field(ColorToken.ACCENT)
    speed: float = Field(
        default=1.0,
        ge=0.1,
        le=3.0,
        multiple_of=0.01,
        description="Animation speed multiplier",
    )
    flame_height: float = Field(
        default=0.35,
        ge=0.1,
        le=1.0,
        multiple_of=0.01,
        description="Flame reach as a fraction of frame height (0.35 = bottom third)",
    )
    smoke_amount: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Smoke density (0 = no smoke, 1 = full smoke)",
    )
    sensitivity: float = Field(
        default=2.5,
        ge=0.1,
        le=8.0,
        multiple_of=0.1,
        description="Audio response gain on bass/amplitude after job-wide normalization",
    )
    opacity: float = Field(default=1.0, ge=0.0, le=1.0, multiple_of=0.1)

    _canvas_h: float = PrivateAttr(default=0.0)
    _bounds_x: float = PrivateAttr(default=0.0)
    _bounds_y: float = PrivateAttr(default=0.0)
    _bounds_w: float = PrivateAttr(default=0.0)
    _bounds_h: float = PrivateAttr(default=0.0)

    _bass_history: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype="f4"))
    _amp_history: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype="f4"))
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
        self._bass_history, _, _, self._amp_history = precompute_bus_drives(bus, total)
        self._beat_decay_frames = _precompute_beat_decay(bus, total)

    def _set_uniform(self, prog: moderngl.Program, name: str, value: Any) -> None:
        if name in prog:
            member = prog[name]
            if isinstance(member, moderngl.Uniform):
                member.value = value

    def _audio_drives_for_frame(
        self,
        ctx: RenderContext,
    ) -> tuple[float, float, float, bool]:
        """Returns bass, amplitude, beat_decay, shader_applies_sensitivity."""
        if not self.bus_active_for_draw(ctx):
            return 0.0, 0.0, 0.0, True
        if self._bass_history.shape[0] > 0:
            f = max(0, min(ctx.time.frame, self._bass_history.shape[0] - 1))
            bass = min(1.0, float(self._bass_history[f]))
            amp = min(1.0, float(self._amp_history[f]))
            beat = (
                float(self._beat_decay_frames[f]) if self._beat_decay_frames.shape[0] > 0 else 0.0
            )
            return bass, amp, beat, True
        af = ctx.audio_bus_frame
        return (
            self.scale_audio(float(af.bass)),
            self.scale_audio(float(af.amplitude)),
            1.5 if af.beat else 0.0,
            False,
        )

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
        self._set_uniform(prog, "u_flame_height", self.flame_height)
        self._set_uniform(prog, "u_smoke_amount", self.smoke_amount)

        bass, amp, beat_decay, shader_sens = self._audio_drives_for_frame(ctx)
        self._set_uniform(
            prog,
            "u_sensitivity",
            float(self.sensitivity) if shader_sens else 1.0,
        )
        self._set_uniform(prog, "u_opacity", self.opacity)

        rf, gf, bf, _ = resolve_color(self.color_fire, ctx.job.colors).rgba
        rs, gs, bs, _ = resolve_color(self.color_sparks, ctx.job.colors).rgba
        self._set_uniform(prog, "u_color_fire", (rf, gf, bf))
        self._set_uniform(prog, "u_color_sparks", (rs, gs, bs))

        self._set_uniform(prog, "u_bass", bass)
        self._set_uniform(prog, "u_amplitude", amp)
        self._set_uniform(prog, "u_beat_decay", beat_decay)

        gl.scissor = (
            int(self._bounds_x),
            int(ctx.job.height - self._bounds_y - ctx.bounds.height),
            int(self._bounds_w),
            int(self._bounds_h),
        )

        assert self._vao is not None
        self._vao.render(moderngl.TRIANGLES)

        gl.scissor = None
