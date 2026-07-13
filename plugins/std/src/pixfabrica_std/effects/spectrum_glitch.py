from __future__ import annotations

from typing import Any, ClassVar

import moderngl
import numpy as np
from pydantic import Field, PrivateAttr

from pixfabrica_core.audio.bus import N_SPECTRUM, AudioBusFrame
from pixfabrica_core.audio.mixin import AudioVisualMixin
from pixfabrica_core.clips import (
    ClipCategory,
    ClipTag,
    GLPostProcessClip,
    PrepareContext,
    RenderContext,
)
from pixfabrica_core.graphics import Rect
from pixfabrica_core.random import SeededRandom

# --- CodePen glitch.js constants (original Web Audio byte scale 0..255) ---
_JS_BYTE_SCALE = 255.0
_JS_BOX_K = 110.0  # boxCount  = ceil((level / k) ** (level / k))
_JS_RGB_K = 70.0  # glitchCount = ceil((level / k) ** (level / k))
_JS_BOX_GATE = 220.0  # random * 100 + level > gate -> drawBoxGlitch2
_JS_LINE_GATE = 300.0  # random * 150 + level > gate -> createGlitchLine
_JS_BOX_RAND_SCALE = 100.0
_JS_LINE_RAND_SCALE = 150.0
_JS_LINE_SHIFT_DIV = 20.0  # bar_shift = fbc_array[y] / 20

# Normalized (0..1 bus) equivalents used in Python + shader uniforms
NORM_BOX_K = _JS_BOX_K / _JS_BYTE_SCALE
NORM_RGB_K = _JS_RGB_K / _JS_BYTE_SCALE
NORM_BOX_GATE = _JS_BOX_GATE / _JS_BYTE_SCALE
NORM_LINE_GATE = _JS_LINE_GATE / _JS_BYTE_SCALE

# Shader magnitude caps (UV / pixel space at strength = 1)
MAX_BLOCK_JUMP_UV = 0.22
MAX_RGB_OFFSET_PX = 48.0
MAX_LINE_SHIFT_PX = 32.0
BLOCK_GRID_MIN = 12.0
BLOCK_GRID_MAX = 48.0

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
uniform vec2  u_resolution;
uniform float u_strength;
uniform float u_opacity;
uniform float u_level;
uniform float u_box_drive;
uniform float u_rgb_drive;
uniform float u_frame;
uniform float u_seed;
uniform float u_box_gate;
uniform float u_line_gate;
uniform float u_box_rand_scale;
uniform float u_line_rand_scale;
uniform float u_line_shift_div;
uniform float u_max_block_jump;
uniform float u_max_rgb_px;
uniform float u_max_line_px;
uniform float u_block_grid_min;
uniform float u_block_grid_max;
uniform float u_spectrum[64];

in vec2 v_uv;
out vec4 fragColor;

float hash1d(float x) {
    return fract(sin(x * 127.1) * 43758.5453);
}

float hash2d(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

float spectrum_at_y(float y) {
    float bin = clamp(y, 0.0, 1.0) * 63.0;
    int i0 = int(floor(bin));
    int i1 = min(i0 + 1, 63);
    float f = fract(bin);
    return mix(u_spectrum[i0], u_spectrum[i1], f);
}

vec2 datamosh_uv(vec2 uv) {
    float drive = clamp(u_box_drive * u_strength, 0.0, 1.0);
    if (drive <= 0.0) {
        return uv;
    }

    float grid = mix(u_block_grid_min, u_block_grid_max, drive);
    vec2 id = floor(uv * grid);
    vec2 f = fract(uv * grid);
    float level_byte = u_level * 255.0;

    float gate_roll = hash2d(id + vec2(u_seed, u_frame * 0.017));
    if (gate_roll * u_box_rand_scale + level_byte <= u_box_gate) {
        return uv;
    }

    float mode = hash2d(id + vec2(1.37, 2.71));
    float jump = u_max_block_jump * drive;

    if (mode > 0.5) {
        vec2 dest_id = mod(id + floor(hash2d(id + vec2(4.17, 9.31)) * grid), grid);
        return (dest_id + f) / grid;
    }

    vec2 delta = (hash2d(id + vec2(5.91, 3.13)) - 0.5) * 2.0 * vec2(jump, jump * 0.35);
    return clamp(uv + delta, 0.0, 1.0);
}

void main() {
    vec3 original = texture(u_source, v_uv).rgb;

    if (u_strength <= 0.0 || u_level <= 0.0 || u_opacity <= 0.0) {
        fragColor = vec4(original, 1.0);
        return;
    }

    vec2 uv = datamosh_uv(v_uv);
    float level_byte = u_level * 255.0;
    float px = 1.0 / max(u_resolution.x, 1.0);

    float rgb_px = u_rgb_drive * u_strength * u_max_rgb_px;
    float rand_r = (hash1d(u_frame + u_seed + 1.1) * 2.0 - 1.0) * rgb_px;
    float rand_g = (hash1d(u_frame + u_seed + 2.2) * 2.0 - 1.0) * rgb_px;
    float rand_b = (hash1d(u_frame + u_seed + 3.3) * 2.0 - 1.0) * rgb_px;

    float line_r = 0.0;
    float line_g = 0.0;
    float line_b = 0.0;
    float row = floor(v_uv.y * u_resolution.y);
    float line_roll = hash1d(row + u_seed + u_frame * 0.031);
    if (line_roll * u_line_rand_scale + level_byte > u_line_gate) {
        float bar_shift = spectrum_at_y(v_uv.y) * 255.0 / max(u_line_shift_div, 1.0);
        line_r = -bar_shift;
        line_g = bar_shift;
        line_b = bar_shift * 2.0;
    }

    float line_cap = u_max_line_px * u_strength;
    line_r = clamp(line_r, -line_cap, line_cap);
    line_g = clamp(line_g, -line_cap, line_cap);
    line_b = clamp(line_b, -line_cap, line_cap);

    vec2 uv_r = clamp(uv + vec2((rand_r + line_r) * px, 0.0), 0.0, 1.0);
    vec2 uv_g = clamp(uv + vec2((rand_g + line_g) * px, 0.0), 0.0, 1.0);
    vec2 uv_b = clamp(uv + vec2((rand_b + line_b) * px, 0.0), 0.0, 1.0);

    vec3 glitched = vec3(
        texture(u_source, uv_r).r,
        texture(u_source, uv_g).g,
        texture(u_source, uv_b).b
    );

    float mix_amt = clamp(max(u_box_drive, u_rgb_drive) * u_strength, 0.0, 1.0);
    vec3 processed = mix(original, glitched, mix_amt);
    fragColor = vec4(mix(original, processed, u_opacity), 1.0);
}
"""

_QUAD = np.array([-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0], dtype="f4")


def level_avg_from_spectrum(spectrum: list[float]) -> float:
    """Mean spectrum energy — JS averaged the first height/2 FFT bins."""
    if not spectrum:
        return 0.0
    return float(sum(spectrum) / len(spectrum))


def self_ref_drive(level: float, k_byte: float) -> float:
    """Port of ``(levelAvg / k) ** (levelAvg / k)`` with level normalized 0..1."""
    if level <= 0.0:
        return 0.0
    k = k_byte / _JS_BYTE_SCALE
    ratio = min(level / k, 4.0)
    return float(ratio**ratio)


def drives_from_level(level: float) -> tuple[float, float]:
    """Return ``(box_drive, rgb_drive)`` for a normalized level average."""
    return (
        self_ref_drive(level, _JS_BOX_K),
        self_ref_drive(level, _JS_RGB_K),
    )


def precompute_spectrum_drives(
    *,
    total_frames: int,
    sensitivity: float,
    bus_select: str | None,
    bus_frames: list[AudioBusFrame] | None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per-frame level average, box drive, and RGB drive arrays."""
    level = np.zeros(total_frames, dtype=np.float32)
    box = np.zeros(total_frames, dtype=np.float32)
    rgb = np.zeros(total_frames, dtype=np.float32)

    if total_frames <= 0:
        return level, box, rgb

    bus_connected = bool((bus_select or "").strip())
    if not bus_connected or not bus_frames:
        return level, box, rgb

    n = min(total_frames, len(bus_frames))
    sens = float(sensitivity)
    for f in range(n):
        af = bus_frames[f]
        lv = min(1.0, max(0.0, level_avg_from_spectrum(af.spectrum) * sens))
        level[f] = lv
        b, r = drives_from_level(lv)
        box[f] = b
        rgb[f] = r

    return level, box, rgb


class SpectrumGlitch(AudioVisualMixin, GLPostProcessClip):
    """Continuous spectrum-reactive datamosh, RGB split, and scanline glitch.

    Driven by audio bus spectrum energy every frame — quiet sections stay clean,
    loud sections ramp block displacement and chromatic tear. Requires ``bus_select``.
    Stack on a GLEffectTrack (``std-post-track``) after VHS/scanlines, alongside
    ``std-glitch`` for onset bursts.
    """

    clip_type: ClassVar[str] = "std-spectrum-glitch"
    clip_category: ClassVar[ClipCategory] = ClipCategory.POSTPROCESS
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED, ClipTag.GL]

    strength: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Overall datamosh, RGB spread, and line-shift magnitude",
    )
    opacity: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Blend between original (0) and glitched (1)",
    )
    seed: int | None = Field(
        default=None,
        description="Random seed for block and line variation; None derives from clip id",
    )

    _program: moderngl.Program | None = PrivateAttr(default=None)
    _vao: moderngl.VertexArray | None = PrivateAttr(default=None)
    _res: tuple[float, float] = PrivateAttr(default=(0.0, 0.0))
    _shader_seed: float = PrivateAttr(default=0.0)
    _bus_connected: bool = PrivateAttr(default=False)
    _level: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype=np.float32))
    _box_drive: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype=np.float32))
    _rgb_drive: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype=np.float32))

    async def prepare(self, ctx: PrepareContext, _bounds: Rect | None = None) -> None:
        self._res = (float(ctx.job.width), float(ctx.job.height))
        rng = (
            SeededRandom(self.seed) if self.seed is not None else SeededRandom.from_string(self.id)
        )
        self._shader_seed = rng.next() * 10000.0
        self._bus_connected = bool((self.bus_select or "").strip())
        self._level, self._box_drive, self._rgb_drive = precompute_spectrum_drives(
            total_frames=max(ctx.job.total_frames, 0),
            sensitivity=float(self.sensitivity),
            bus_select=self.bus_select,
            bus_frames=self.bus_timeline(ctx),
        )

    def _set_uniform(self, prog: moderngl.Program, name: str, value: Any) -> None:
        if name in prog:
            member = prog[name]
            if isinstance(member, moderngl.Uniform):
                member.value = value

    def _frame_index(self, ctx: RenderContext) -> int:
        if self._level.size:
            return max(0, min(ctx.time.frame, self._level.shape[0] - 1))
        return max(0, ctx.time.frame)

    def draw(self, ctx: RenderContext) -> None:
        if ctx.source_texture is None:
            return

        gl: moderngl.Context = ctx.canvas

        if self._program is None:
            self._program = gl.program(vertex_shader=_VERT, fragment_shader=_FRAG)
            vbo = gl.buffer(_QUAD.tobytes())
            self._vao = gl.simple_vertex_array(self._program, vbo, "in_vert")

        f = self._frame_index(ctx)
        if self._bus_connected and self._level.size:
            level = float(self._level[f])
            box_drive = float(self._box_drive[f])
            rgb_drive = float(self._rgb_drive[f])
            spectrum = list(ctx.audio_bus_frame.spectrum[:N_SPECTRUM])
        else:
            level = 0.0
            box_drive = 0.0
            rgb_drive = 0.0
            spectrum = [0.0] * N_SPECTRUM

        prog = self._program
        ctx.source_texture.use(location=0)
        self._set_uniform(prog, "u_source", 0)
        self._set_uniform(prog, "u_resolution", self._res)
        self._set_uniform(prog, "u_strength", float(self.strength))
        self._set_uniform(prog, "u_opacity", float(self.opacity))
        self._set_uniform(prog, "u_level", level)
        self._set_uniform(prog, "u_box_drive", box_drive)
        self._set_uniform(prog, "u_rgb_drive", rgb_drive)
        self._set_uniform(prog, "u_frame", float(ctx.time.frame))
        self._set_uniform(prog, "u_seed", self._shader_seed)
        self._set_uniform(prog, "u_box_gate", _JS_BOX_GATE)
        self._set_uniform(prog, "u_line_gate", _JS_LINE_GATE)
        self._set_uniform(prog, "u_box_rand_scale", _JS_BOX_RAND_SCALE)
        self._set_uniform(prog, "u_line_rand_scale", _JS_LINE_RAND_SCALE)
        self._set_uniform(prog, "u_line_shift_div", _JS_LINE_SHIFT_DIV)
        self._set_uniform(prog, "u_max_block_jump", MAX_BLOCK_JUMP_UV)
        self._set_uniform(prog, "u_max_rgb_px", MAX_RGB_OFFSET_PX)
        self._set_uniform(prog, "u_max_line_px", MAX_LINE_SHIFT_PX)
        self._set_uniform(prog, "u_block_grid_min", BLOCK_GRID_MIN)
        self._set_uniform(prog, "u_block_grid_max", BLOCK_GRID_MAX)

        if "u_spectrum[0]" in prog:
            for i in range(N_SPECTRUM):
                self._set_uniform(prog, f"u_spectrum[{i}]", float(spectrum[i]))

        assert self._vao is not None
        self._vao.render(moderngl.TRIANGLES)
