from __future__ import annotations

import math
from typing import Any, ClassVar

import moderngl
import numpy as np
from pydantic import Field, PrivateAttr, field_validator

from pixfabrica_core.audio.bus import AudioBusFrame
from pixfabrica_core.audio.mixin import AudioVisualMixin
from pixfabrica_core.clips import ClipCategory, ClipGL, ClipTag, PrepareContext, RenderContext
from pixfabrica_core.graphics import Rect
from pixfabrica_core.theme.color import Color, ColorToken, color_field, resolve_color
from pixfabrica_std.tilt import ANGLE_FULL_DESC, ANGLE_FULL_MAX, ANGLE_FULL_MIN

_MAX_BARS = 7

# Baked motion / layout (kidbashing defaults).
_PULSE_AMP = 0.13
_PULSE_PERIOD_SEC = 1.9
_RIPPLE_AMP = 0.08
_RIPPLE_PERIOD_SEC = 1.25
_FLUTTER_AMP = 0.045
_FLUTTER_PERIOD_SEC = 0.95
_MIN_HEIGHT_FRAC = 0.15  # floor when bus is active but signal is silent
_MAX_HEIGHT_FRAC = 0.65
_CLUSTER_HALF_W = 0.5
_AMP_FLOOR = 0.30  # keep cluster visible in quiet sections

# Maps distance-from-center to band index (0=bass, 1=mid, 2=high).
# Distance 3 reuses high — only reached at bar_count=7.
_BAND_FOR_DISTANCE = (0, 1, 2, 2)

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

uniform float u_offset_x;
uniform float u_offset_y;
uniform float u_scale;
uniform float u_angle;

uniform float u_bar_heights[7];
uniform float u_bar_count_f;
uniform float u_bar_gap_ratio;
uniform float u_max_height;
uniform float u_cluster_half_w;

uniform vec3  u_color_tl;
uniform vec3  u_color_tr;
uniform vec3  u_color_bl;
uniform vec3  u_color_br;

uniform float u_glow_intensity;

out vec4 frag_color;

float capsule_sdf(vec2 p, vec2 a, vec2 b, float r) {
    vec2 pa = p - a, ba = b - a;
    float h = clamp(dot(pa, ba) / dot(ba, ba), 0.0, 1.0);
    return length(pa - ba * h) - r;
}

vec3 sample_gradient(vec2 grad_uv) {
    vec3 top = mix(u_color_tl, u_color_tr, grad_uv.x);
    vec3 bot = mix(u_color_bl, u_color_br, grad_uv.x);
    return mix(top, bot, grad_uv.y);
}

void main() {
    float px = gl_FragCoord.x - u_origin.x;
    float py = (u_canvas_h - gl_FragCoord.y) - u_origin.y;

    float anchor_x = u_res.x * u_offset_x;
    float anchor_y = u_res.y * u_offset_y;
    float norm = max(length(u_res), 1.0);
    vec2 uv = vec2(px - anchor_x, anchor_y - py) / norm;

    float a = radians(u_angle);
    uv *= mat2(cos(a), -sin(a), sin(a), cos(a));
    uv /= max(u_scale, 0.001);

    int n = int(u_bar_count_f);
    float slot_w = (u_cluster_half_w * 2.0) / u_bar_count_f;
    float half_w = slot_w * (1.0 - u_bar_gap_ratio) * 0.5;
    float max_half_h = u_max_height * 0.5;

    float d_min = 1e9;
    for (int i = 0; i < 7; i++) {
        if (i >= n) break;
        float bar_h = u_bar_heights[i] * u_max_height;
        if (bar_h < 0.001) continue;

        float cx = -u_cluster_half_w + (float(i) + 0.5) * slot_w;
        float half_h = bar_h * 0.5;
        float inner_r = min(half_w, half_h);

        vec2 cap_a = vec2(cx, -half_h + inner_r);
        vec2 cap_b = vec2(cx, half_h - inner_r);
        d_min = min(d_min, capsule_sdf(uv, cap_a, cap_b, inner_r));
    }

    float aa = 1.5 / norm;
    float core = 1.0 - smoothstep(-aa, aa, d_min);
    float spread = max(half_w * u_glow_intensity * 3.0 + 0.001, 0.001);
    float glow = exp(-max(d_min, 0.0) / spread) * u_glow_intensity;
    float alpha = max(core, glow);
    if (alpha < 0.001) {
        frag_color = vec4(0.0);
        return;
    }

    vec2 grad_uv = vec2(
        (uv.x + u_cluster_half_w) / (u_cluster_half_w * 2.0),
        (uv.y + max_half_h) / max(u_max_height, 0.001)
    );
    grad_uv = clamp(grad_uv, 0.0, 1.0);
    vec3 col = sample_gradient(grad_uv);
    frag_color = vec4(col * alpha, alpha);
}
"""

_QUAD = np.array([-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, 1.0], dtype="f4")


def _silhouette(distance: int, max_distance: int) -> float:
    """Fixed symmetric arch — center tallest, mirrored pairs share height."""
    if distance == 0:
        return 1.0
    if distance == 1:
        return 0.78
    if distance == 2:
        return 0.92
    if distance == 3:
        return 0.55
    if max_distance <= 3:
        return 0.55
    t = (distance - 3) / max(max_distance - 3, 1)
    return max(0.32, 0.55 * (1.0 - 0.45 * t))


def _idle_scale(t_sec: float, distance: int, speed: float) -> float:
    """Symmetric idle motion: shared pulse plus light additive ripple/flutter."""
    t = t_sec * max(speed, 0.1)
    pulse = 1.0 + _PULSE_AMP * math.sin(2.0 * math.pi * t / _PULSE_PERIOD_SEC)
    ripple = _RIPPLE_AMP * math.sin(2.0 * math.pi * t / _RIPPLE_PERIOD_SEC + float(distance) * 0.85)
    flutter = _FLUTTER_AMP * math.sin(
        2.0 * math.pi * t / _FLUTTER_PERIOD_SEC + float(distance) * 1.35
    )
    return pulse + ripple + flutter


def _slot_silhouettes(half_slots: int, max_distance: int) -> np.ndarray:
    return np.array(
        [_silhouette(d, max_distance) for d in range(half_slots)],
        dtype="f4",
    )


def _keep_center_tallest(slot_heights: np.ndarray) -> np.ndarray:
    """Preserve arch shape: center slot stays strictly above mirrored pairs."""
    out = slot_heights.copy()
    center = float(out[0])
    for d in range(1, len(out)):
        out[d] = min(float(out[d]), center - 0.022 - 0.01 * (d - 1))
    return out


def _normalize_band_timeline(raw: np.ndarray) -> np.ndarray:
    """Stretch each band column to ~0..1 using robust job-wide percentiles.

    Analyzers disagree on absolute band scale (legacy per-frame max vs log
    job-wide norm). Normalizing once over the whole bus timeline makes capsule
    bars react with similar punch regardless of analyzer backend.
    """
    if raw.size == 0:
        return raw
    out = np.empty_like(raw)
    for col in range(raw.shape[1]):
        channel = raw[:, col]
        lo, hi = np.percentile(channel, (5.0, 95.0))
        span = max(float(hi - lo), 1e-6)
        out[:, col] = np.clip((channel - lo) / span, 0.0, 1.0)
    return out


def _bus_band_drives(frame: AudioBusFrame) -> tuple[float, float, float]:
    """Map bus payload to per-band 0..1 drives (bass, mid, high)."""
    bass = min(1.0, max(0.0, float(frame.bass)))
    mid = min(1.0, max(0.0, float(frame.mid)))
    high = min(1.0, max(0.0, float(frame.high)))
    return bass, mid, high


class CapsuleBarsGL(AudioVisualMixin, ClipGL):
    """Center-anchored symmetric capsule bars with a shared bilinear theme gradient."""

    clip_type: ClassVar[str] = "std-capsule-bars-gl"
    clip_category: ClassVar[ClipCategory] = ClipCategory.AUDIO
    clip_tags: ClassVar[list[str]] = [
        ClipTag.AUDIO_REACTIVE,
        ClipTag.ANIMATED,
        ClipTag.GL,
    ]

    bar_count: int = Field(
        default=3,
        ge=3,
        le=_MAX_BARS,
        multiple_of=1,
        description="Number of bars (odd values only). Symmetric around the center.",
    )
    bar_gap: float = Field(
        default=0.22,
        ge=0.0,
        le=0.70,
        multiple_of=0.02,
        description="Fraction of each bar slot used as gap between capsules.",
    )
    color_tl: ColorToken | Color = color_field(ColorToken.SECONDARY)
    color_tr: ColorToken | Color = color_field(ColorToken.PRIMARY)
    color_bl: ColorToken | Color = color_field(ColorToken.ACCENT)
    color_br: ColorToken | Color = color_field(ColorToken.BACKGROUND)
    offset_x: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Horizontal anchor (0 = left, 0.5 = center, 1 = right).",
    )
    offset_y: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Vertical anchor (0 = top, 0.5 = center, 1 = bottom).",
    )
    width: float = Field(
        default=0.15,
        ge=0.05,
        le=1.50,
        multiple_of=0.05,
        description="Cluster width as a fraction of the container (1.0 = full width).",
    )
    angle: float = Field(
        default=0.0,
        ge=ANGLE_FULL_MIN,
        le=ANGLE_FULL_MAX,
        multiple_of=1.0,
        description=ANGLE_FULL_DESC,
    )
    speed: float = Field(
        default=1.4,
        ge=0.25,
        le=4.0,
        multiple_of=0.05,
        description="Idle bar animation speed multiplier.",
    )
    smoothing: float = Field(
        default=0.45,
        ge=0.0,
        le=0.95,
        multiple_of=0.05,
        description="Temporal smoothing on bus band drives (0 = raw, 0.95 = sluggish).",
    )
    sensitivity: float = Field(
        default=2.5,
        ge=0.1,
        le=8.0,
        multiple_of=0.1,
        description="Audio response gain on band drives after job-wide normalization",
    )
    glow_intensity: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Neon bloom spread around each bar (0 = crisp edges, 1 = wide glow)",
    )

    _canvas_h: float = PrivateAttr(default=0.0)
    _bounds_x: float = PrivateAttr(default=0.0)
    _bounds_y: float = PrivateAttr(default=0.0)
    _bounds_w: float = PrivateAttr(default=0.0)
    _bounds_h: float = PrivateAttr(default=0.0)

    _program: moderngl.Program | None = PrivateAttr(default=None)
    _vao: moderngl.VertexArray | None = PrivateAttr(default=None)
    _bar_history: np.ndarray = PrivateAttr(
        default_factory=lambda: np.zeros((0, _MAX_BARS), dtype="f4")
    )
    _drive_history: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros((0, 3), dtype="f4"))
    _amp_history: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype="f4"))
    _silhouettes: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype="f4"))
    _center: int = PrivateAttr(default=0)
    _diag: float = PrivateAttr(default=1.0)

    @field_validator("bar_count", mode="before")
    @classmethod
    def _coerce_odd(cls, v: object) -> int:
        n = int(v)  # type: ignore[arg-type]
        if n % 2 == 0:
            n = min(n + 1, _MAX_BARS) if n < _MAX_BARS else n - 1
        return max(3, min(_MAX_BARS, n))

    async def prepare(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        b = bounds or Rect(0, 0, ctx.job.width, ctx.job.height)
        self._canvas_h = float(ctx.job.height)
        self._bounds_x = float(b.x)
        self._bounds_y = float(b.y)
        self._bounds_w = float(b.width)
        self._bounds_h = float(b.height)
        self._diag = math.sqrt(self._bounds_w**2 + self._bounds_h**2)

        n = self.bar_count
        self._center = n // 2
        half_slots = (n + 1) // 2
        max_distance = half_slots - 1
        self._silhouettes = _slot_silhouettes(half_slots, max_distance)

        self._bar_history = self._precompute_bar_history(ctx)
        self._drive_history, self._amp_history = self._precompute_drive_history(ctx)

    def _precompute_bar_history(self, ctx: PrepareContext) -> np.ndarray:
        total = max(ctx.job.total_frames, 0)
        history = np.zeros((total, _MAX_BARS), dtype="f4")
        if total == 0:
            return history

        n = self.bar_count
        center = n // 2
        half_slots = (n + 1) // 2
        max_distance = half_slots - 1
        silhouettes = _slot_silhouettes(half_slots, max_distance)

        fps = max(float(ctx.job.fps), 1.0)
        anim_speed = float(self.speed)

        for f in range(total):
            t_sec = f / fps

            slot_heights = silhouettes * np.array(
                [_idle_scale(t_sec, d, anim_speed) for d in range(half_slots)],
                dtype="f4",
            )
            slot_heights = _keep_center_tallest(slot_heights)

            for i in range(n):
                history[f, i] = float(slot_heights[abs(i - center)])

        return history

    def _precompute_drive_history(self, ctx: PrepareContext) -> tuple[np.ndarray, np.ndarray]:
        total = max(ctx.job.total_frames, 0)
        history = np.zeros((total, 3), dtype="f4")  # columns: [bass, mid, high]
        amp_history = np.zeros(total, dtype="f4")
        if total == 0:
            return history, amp_history

        bus_frames: list[AudioBusFrame] = self.bus_timeline(ctx) or []
        if not bus_frames:
            return history, amp_history

        n_bus = min(total, len(bus_frames))
        raw = np.zeros((n_bus, 3), dtype="f4")
        amp_raw = np.zeros(n_bus, dtype="f4")
        for f in range(n_bus):
            frame = bus_frames[f]
            raw[f, 0] = float(frame.bass)
            raw[f, 1] = float(frame.mid)
            raw[f, 2] = float(frame.high)
            amp_raw[f] = float(frame.amplitude)
        targets = np.clip(
            _normalize_band_timeline(raw) * float(self.sensitivity),
            0.0,
            1.0,
        )
        amp_targets = np.clip(
            _normalize_band_timeline(amp_raw.reshape(-1, 1)).reshape(-1) * float(self.sensitivity),
            0.0,
            1.0,
        )

        decay = float(self.smoothing)
        attack = min(0.12, max(decay * 0.25, 0.04)) if decay > 0.0 else 0.0

        drives_smooth = np.zeros(3, dtype="f4")
        amp_smooth = 0.0
        for f in range(total):
            if f < n_bus:
                is_attack = targets[f] > drives_smooth
                band_s = np.where(is_attack, attack, decay)
                band_1ms = 1.0 - band_s
                drives_smooth = drives_smooth * band_s + targets[f] * band_1ms

                amp_s = attack if amp_targets[f] > amp_smooth else decay
                amp_smooth = amp_smooth * amp_s + float(amp_targets[f]) * (1.0 - amp_s)
            else:
                drives_smooth = drives_smooth * decay
                amp_smooth *= decay

            history[f] = drives_smooth
            amp_history[f] = amp_smooth

        return history, amp_history

    def _set_uniform(self, prog: moderngl.Program, name: str, value: Any) -> None:
        if name in prog:
            member = prog[name]
            if isinstance(member, moderngl.Uniform):
                member.value = value

    def _set_bar_heights(self, prog: moderngl.Program, bar_heights: np.ndarray, n: int) -> None:
        padded = tuple(float(bar_heights[i]) if i < n else 0.0 for i in range(_MAX_BARS))
        if "u_bar_heights[0]" in prog:
            for i in range(n):
                self._set_uniform(prog, f"u_bar_heights[{i}]", float(bar_heights[i]))
        elif "u_bar_heights" in prog:
            member = prog["u_bar_heights"]
            if isinstance(member, moderngl.Uniform):
                member.value = padded  # type: ignore[assignment]

    def _bus_bar_heights(self, band_drives: np.ndarray, amp_drive: float, n: int) -> np.ndarray:
        """Per-bar heights from band drives with silhouette ceiling and center dominance."""
        bar_heights = np.zeros(_MAX_BARS, dtype="f4")
        center = self._center
        half_slots = (n + 1) // 2
        slot_heights = np.zeros(half_slots, dtype="f4")
        for d in range(half_slots):
            band_idx = _BAND_FOR_DISTANCE[min(d, len(_BAND_FOR_DISTANCE) - 1)]
            drive = float(band_drives[band_idx])
            sil = float(self._silhouettes[min(d, len(self._silhouettes) - 1)])
            raw_h = sil * max(_MIN_HEIGHT_FRAC, drive)
            floor_h = sil * _MIN_HEIGHT_FRAC
            amp_scale = _AMP_FLOOR + (1.0 - _AMP_FLOOR) * float(np.clip(amp_drive, 0.0, 1.0))
            slot_heights[d] = floor_h + (raw_h - floor_h) * amp_scale
        slot_heights = _keep_center_tallest(slot_heights)
        for i in range(n):
            bar_heights[i] = float(slot_heights[abs(i - center)])
        return bar_heights

    def draw(self, ctx: RenderContext) -> None:
        gl: moderngl.Context = ctx.canvas

        if self._program is None:
            self._program = gl.program(vertex_shader=_VERT, fragment_shader=_FRAG)
            vbo = gl.buffer(_QUAD.tobytes())
            self._vao = gl.simple_vertex_array(self._program, vbo, "in_vert")

        prog = self._program
        n = self.bar_count

        if self.bus_active_for_draw(ctx):
            if self._drive_history.shape[0] > 0:
                f_idx = max(0, min(ctx.time.frame, self._drive_history.shape[0] - 1))
                band_drives = self._drive_history[f_idx]
                amp_drive = float(self._amp_history[f_idx]) if self._amp_history.size else 0.0
            else:
                af = ctx.audio_bus_frame
                band_drives = np.clip(
                    np.array(_bus_band_drives(af), dtype="f4") * float(self.sensitivity),
                    0.0,
                    1.0,
                )
                amp_drive = min(
                    1.0,
                    float(np.clip(af.amplitude, 0.0, 1.0)) * float(self.sensitivity),
                )
            bar_heights = self._bus_bar_heights(band_drives, amp_drive, n)
        else:
            if self._bar_history.shape[0] > 0:
                frame = max(0, min(ctx.time.frame, self._bar_history.shape[0] - 1))
                bar_heights = self._bar_history[frame]
            else:
                bar_heights = np.zeros(_MAX_BARS, dtype="f4")

        tlr, tlg, tlb, _ = resolve_color(self.color_tl, ctx.job.colors).rgba
        trr, trg, trb, _ = resolve_color(self.color_tr, ctx.job.colors).rgba
        blr, blg, blb, _ = resolve_color(self.color_bl, ctx.job.colors).rgba
        brr, brg, brb, _ = resolve_color(self.color_br, ctx.job.colors).rgba

        self._set_uniform(prog, "u_res", (self._bounds_w, self._bounds_h))
        self._set_uniform(prog, "u_origin", (self._bounds_x, self._bounds_y))
        self._set_uniform(prog, "u_canvas_h", self._canvas_h)
        self._set_uniform(prog, "u_offset_x", self.offset_x)
        self._set_uniform(prog, "u_offset_y", self.offset_y)
        self._set_uniform(prog, "u_scale", self.width * self._bounds_w / max(self._diag, 1.0))
        self._set_uniform(prog, "u_angle", self.angle)
        self._set_uniform(prog, "u_bar_count_f", float(n))
        self._set_uniform(prog, "u_bar_gap_ratio", self.bar_gap)
        self._set_uniform(prog, "u_max_height", _MAX_HEIGHT_FRAC)
        self._set_uniform(prog, "u_cluster_half_w", _CLUSTER_HALF_W)
        self._set_uniform(prog, "u_color_tl", (tlr, tlg, tlb))
        self._set_uniform(prog, "u_color_tr", (trr, trg, trb))
        self._set_uniform(prog, "u_color_bl", (blr, blg, blb))
        self._set_uniform(prog, "u_color_br", (brr, brg, brb))
        self._set_uniform(prog, "u_glow_intensity", self.glow_intensity)
        self._set_bar_heights(prog, bar_heights, n)

        bnd = ctx.bounds
        gl.scissor = (
            int(self._bounds_x),
            int(ctx.job.height - self._bounds_y - bnd.height),
            int(self._bounds_w),
            int(bnd.height),
        )

        assert self._vao is not None
        self._vao.render(moderngl.TRIANGLES)

        gl.scissor = None
