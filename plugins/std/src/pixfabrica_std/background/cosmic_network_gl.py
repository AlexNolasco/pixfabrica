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

# Adapted from "The Universe Within" by Martijn Steinrucken aka BigWings (2018)
# https://www.shadertoy.com/view/lscczl — CC BY-NC-SA 3.0
# Changes: removed mouse/iChannel0 dependencies; added audio uniforms, theme
# color tokens, grid_density/layers params, and luma-derived alpha.
_FRAG = """
#version 330 core

uniform vec2  u_res;
uniform vec2  u_origin;
uniform float u_canvas_h;
uniform float u_t;
uniform float u_speed;
uniform float u_layers;
uniform float u_grid_density;
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
uniform float u_rotate;

out vec4 frag_color;

#define S(a, b, t) smoothstep(a, b, t)

float N21(vec2 p) {
    vec3 a = fract(vec3(p.xyx) * vec3(213.897, 653.453, 253.098));
    a += dot(a, a.yzx + 79.76);
    return fract((a.x + a.y) * a.z);
}

vec2 GetPos(vec2 id, vec2 offs, float t) {
    float n  = N21(id + offs);
    float n1 = fract(n * 10.);
    float n2 = fract(n * 100.);
    float a  = t + n;
    return offs + vec2(sin(a * n1), cos(a * n2)) * .4;
}

float df_line(in vec2 a, in vec2 b, in vec2 p) {
    vec2  pa = p - a, ba = b - a;
    float h  = clamp(dot(pa, ba) / dot(ba, ba), 0., 1.);
    return length(pa - ba * h);
}

float line(vec2 a, vec2 b, vec2 uv) {
    float d  = df_line(a, b, uv);
    float d2 = length(a - b);
    float fade = S(1.5, .5, d2) + S(.05, .02, abs(d2 - .75));
    return S(.04, .01, d) * fade;
}

// mid_boost: how much mid-range audio inflates sparkle phase intensity
// high_boost: how much treble audio inflates sparkle emission brightness
float NetLayer(vec2 st, float n, float t, float mid_boost, float high_boost) {
    vec2 id = floor(st) + n;
    st = fract(st) - .5;

    vec2 p[9];
    int  k = 0;
    for (float y = -1.; y <= 1.; y++)
        for (float x = -1.; x <= 1.; x++)
            p[k++] = GetPos(id, vec2(x, y), t);

    float m       = 0.;
    float sparkle = 0.;
    for (int i = 0; i < 9; i++) {
        m += line(p[4], p[i], st);
        float d     = length(st - p[i]);
        float s     = .005 / (d * d);
        s          *= S(1., .7, d);
        float pulse = sin((fract(p[i].x) + fract(p[i].y) + t) * 5.) * .4 + .6;
        pulse       = pow(pulse, 20.);
        s          *= pulse;
        sparkle    += s;
    }

    m += line(p[1], p[3], st);
    m += line(p[1], p[5], st);
    m += line(p[7], p[5], st);
    m += line(p[7], p[3], st);

    // Base sparkle phase — pulses slowly over time
    float sPhase  = (sin(t + n) + sin(t * .1)) * .25 + .5;
    sPhase       += pow(sin(t * .1) * .5 + .5, 50.) * 5.;
    // Mid range audio swells the phase envelope; treble brightens sparkle emission
    sPhase *= 1.0 + mid_boost * 1.5;
    m      += sparkle * sPhase * (1.0 + high_boost * 2.0);

    return m;
}

void main() {
    float px = gl_FragCoord.x - u_origin.x;
    float py = (u_canvas_h - gl_FragCoord.y) - u_origin.y;

    if (px < 0.0 || px >= u_res.x || py < 0.0 || py >= u_res.y) discard;

    vec2 uv = (vec2(px, py) - u_res * .5) / u_res.y;

    float t = u_t * .1 * u_speed;

    // Beat-driven rotation snap: pre-computed decay adds a brief extra spin on each beat.
    // u_rotate == 0 freezes the rotation matrix at identity.
    float beat_rot = u_beat_decay * 0.4 * u_rotate;
    float rot_t    = t * u_rotate + beat_rot;
    float s_rot    = sin(rot_t);
    float c_rot    = cos(rot_t);
    mat2  rot      = mat2(c_rot, -s_rot, s_rot, c_rot);
    vec2  st       = uv * rot;

    float mid_boost  = u_mid  * u_sensitivity;
    float high_boost = u_high * u_sensitivity;

    float m = 0.;
    for (float i = 0.; i < 8.; i += 1.) {
        if (i >= u_layers) break;
        float phase = i / u_layers;
        float z     = fract(t + phase);
        // Bass pulse: kicks briefly expand the zoom rush toward the camera
        float bass_zoom = 1.0 + u_bass * u_sensitivity * 0.5;
        float size      = mix(15., 1., z) * u_grid_density * bass_zoom;
        float fade      = S(0., .6, z) * S(1., .8, z);
        m += fade * NetLayer(st * size, phase, u_t * u_speed, mid_boost, high_boost);
    }

    // Floor glow: amplitude lifts a haze from the bottom of the frame
    float glow = max(-uv.y, 0.0) * u_amplitude * u_sensitivity * 1.5;

    // Color: primary=network lines, secondary=floor glow, accent=hot sparkle overdrive
    vec3 col  = u_color_primary * m;
    col      += u_color_secondary * glow;

    // Accent tints bright overdrive regions (sparkle halos above baseline)
    float hot = clamp(m - 0.8, 0.0, 2.0) * (1.0 + high_boost);
    col      += u_color_accent * hot * 0.6;

    // Amplitude brightens the whole field uniformly
    col *= 1.0 + u_amplitude * u_sensitivity * 0.4;

    // Radial vignette darkens corners
    col *= 1.0 - dot(uv, uv) * 0.8;

    // Luma-derived alpha: dark void stays transparent so lower layers show through
    float luma  = max(col.r, max(col.g, col.b));
    float alpha = smoothstep(0.05, 0.3, luma) * u_opacity;

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


class CosmicNetworkGL(AudioVisualMixin, ClipGL):
    """Layered glowing node-webs fly toward the camera with full multi-band audio
    reactivity: bass zooms, mid shimmers sparkles, high crackles the lines, beat
    snaps the rotation. Based on 'The Universe Within' by Martijn Steinrucken."""

    clip_type: ClassVar[str] = "std-cosmic-network-gl"
    clip_license: ClassVar[str] = "CC-BY-NC-SA-3.0"
    clip_category: ClassVar[ClipCategory] = ClipCategory.BACKGROUND
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED, ClipTag.GL, ClipTag.AUDIO_REACTIVE]

    color_primary: ColorToken | Color = color_field(ColorToken.PRIMARY)
    color_secondary: ColorToken | Color = color_field(ColorToken.SECONDARY)
    color_accent: ColorToken | Color = color_field(ColorToken.ACCENT)
    speed: float = Field(
        default=1.0,
        ge=0.1,
        le=2.5,
        multiple_of=0.01,
        description="Base animation speed multiplier",
    )
    layers: int = Field(
        default=4,
        ge=2,
        le=6,
        multiple_of=1,
        description="Number of overlapping network layers (2=airy, 6=dense)",
    )
    grid_density: float = Field(
        default=1.0,
        ge=0.25,
        le=3.0,
        multiple_of=0.25,
        description="Node grid density per layer (higher = more star nodes visible)",
    )
    rotate: bool = Field(default=False, description="Rotate the network over time")
    sensitivity: float = Field(
        default=2.5,
        ge=0.1,
        le=8.0,
        multiple_of=0.1,
        description="Audio response gain on bass/mid/high/amplitude after job-wide normalization",
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

    _bass_history: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype="f4"))
    _mid_history: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype="f4"))
    _high_history: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype="f4"))
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
        self._bass_history, self._mid_history, self._high_history, self._amp_history = (
            precompute_bus_drives(bus, total)
        )
        self._beat_decay_frames = _precompute_beat_decay(bus, total)

    def _set_uniform(self, prog: moderngl.Program, name: str, value: Any) -> None:
        if name in prog:
            member = prog[name]
            if isinstance(member, moderngl.Uniform):
                member.value = value

    def _audio_drives_for_frame(
        self,
        ctx: RenderContext,
    ) -> tuple[float, float, float, float, float, bool]:
        """Returns bass, mid, high, amp, beat_decay, shader_applies_sensitivity."""
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
        self._set_uniform(prog, "u_layers", float(self.layers))
        self._set_uniform(prog, "u_grid_density", self.grid_density)

        bass, mid, high, amp, beat_decay, shader_sens = self._audio_drives_for_frame(ctx)
        self._set_uniform(
            prog,
            "u_sensitivity",
            float(self.sensitivity) if shader_sens else 1.0,
        )
        self._set_uniform(prog, "u_opacity", self.opacity)

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
        self._set_uniform(prog, "u_rotate", 1.0 if self.rotate else 0.0)

        gl.scissor = (
            int(self._bounds_x),
            int(ctx.job.height - self._bounds_y - ctx.bounds.height),
            int(self._bounds_w),
            int(self._bounds_h),
        )

        assert self._vao is not None
        self._vao.render(moderngl.TRIANGLES)

        gl.scissor = None
