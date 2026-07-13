from __future__ import annotations

import math
from typing import Any, cast

import moderngl
import numpy as np

from pixfabrica_core.audio.bus import AudioBusFrame
from pixfabrica_core.graphics import Rect

DEFAULT_CAMERA_DISTANCE = 2.2
DEFAULT_BASS_SMOOTHING = 0.45
DEFAULT_SHAPEKEY_ATTACK_SEC = 0.05
DEFAULT_SHAPEKEY_RELEASE_SEC = 0.15

LAMBERT_MESH_VERT = """
#version 330 core
in vec3 in_pos;
in vec3 in_normal;
uniform mat4 u_mvp;
uniform mat3 u_normal_matrix;
out vec3 v_normal;
void main() {
    v_normal = u_normal_matrix * in_normal;
    gl_Position = u_mvp * vec4(in_pos, 1.0);
}
"""

LAMBERT_MESH_FRAG = """
#version 330 core
in vec3 v_normal;
uniform vec3 u_mesh_color;
uniform vec3 u_light_color;
uniform vec3 u_light_dir;
uniform float u_ambient;
uniform float u_opacity;
out vec4 frag_color;
void main() {
    vec3 n = normalize(v_normal);
    vec3 l = normalize(u_light_dir);
    float diff = max(dot(n, l), 0.0);
    vec3 lit = u_mesh_color * (u_ambient + (1.0 - u_ambient) * diff) * u_light_color;
    frag_color = vec4(lit * u_opacity, u_opacity);
}
"""


def set_uniform(prog: moderngl.Program, name: str, value: Any) -> None:
    if name not in prog:
        return
    member = prog[name]
    if not isinstance(member, moderngl.Uniform):
        return
    uniform = cast(moderngl.Uniform, member)
    if isinstance(value, (bytes, bytearray)):
        uniform.write(value)
    else:
        uniform.value = value


def write_mvp(prog: moderngl.Program, mvp: np.ndarray) -> None:
    set_uniform(prog, "u_mvp", mvp.T.astype("f4").tobytes())


def write_normal_matrix(prog: moderngl.Program, model_view: np.ndarray) -> None:
    nm = model_view[:3, :3].astype("f4")
    set_uniform(prog, "u_normal_matrix", tuple(nm.T.flatten()))


def upload_indexed_mesh(
    gl: moderngl.Context,
    program: moderngl.Program,
    interleaved: np.ndarray,
    indices: np.ndarray,
) -> moderngl.VertexArray:
    vbo = gl.buffer(interleaved.tobytes())
    ibo = gl.buffer(indices.astype(np.uint32).tobytes())
    return gl.vertex_array(
        program,
        [(vbo, "3f 3f", "in_pos", "in_normal")],
        index_buffer=ibo,
    )


def _bus_driver_scalar(frame: AudioBusFrame, driver: str) -> float:
    if driver == "bass":
        return float(frame.bass)
    if driver == "mid":
        return float(frame.mid)
    if driver == "high":
        return float(frame.high)
    return float(frame.amplitude)


def precompute_shapekey_weight(
    frames: list[AudioBusFrame] | None,
    total: int,
    *,
    fps: float,
    driver: str,
    sensitivity: float,
    max_morph: float,
    attack_sec: float,
    release_sec: float,
) -> np.ndarray:
    """Asymmetric attack/release envelope over a job-normalized bus driver."""
    out = np.zeros(max(total, 0), dtype=np.float32)
    if total <= 0 or not frames:
        return out

    n_bus = min(total, len(frames))
    raw = np.asarray(
        [_bus_driver_scalar(frames[f], driver) for f in range(n_bus)],
        dtype=np.float32,
    )
    normalized = normalize_bus_scalar(raw)
    cap = max(0.0, min(1.0, float(max_morph)))
    sens = max(0.0, float(sensitivity))

    attack_alpha = 1.0 - math.exp(-1.0 / max(float(fps) * max(attack_sec, 1e-4), 1.0))
    release_alpha = 1.0 - math.exp(-1.0 / max(float(fps) * max(release_sec, 1e-4), 1.0))
    state = 0.0
    for f in range(n_bus):
        target = min(cap, max(0.0, float(normalized[f]) * sens))
        alpha = attack_alpha if target > state else release_alpha
        state += (target - state) * alpha
        out[f] = state
    for f in range(n_bus, total):
        state += (0.0 - state) * release_alpha
        out[f] = state
    return out


def bass_zoom(bus_active: bool, sensitivity: float, bass: float) -> float:
    if not bus_active:
        return 1.0
    return 1.0 + sensitivity * max(0.0, min(1.0, float(bass)))


def normalize_bus_scalar(raw: np.ndarray) -> np.ndarray:
    """Stretch a bus scalar timeline to ~0..1 using robust job-wide percentiles."""
    if raw.size == 0:
        return raw
    lo, hi = np.percentile(raw, (5.0, 95.0))
    span = max(float(hi - lo), 1e-6)
    return np.clip((raw - lo) / span, 0.0, 1.0).astype(np.float32)


def precompute_bass_drive(
    frames: list[AudioBusFrame] | None,
    total: int,
    *,
    smoothing: float = DEFAULT_BASS_SMOOTHING,
) -> np.ndarray:
    """Job-normalized, EMA-smoothed bass timeline for mesh audio reactions."""
    bass, _, _, _ = precompute_bus_drives(frames, total, smoothing=smoothing)
    return bass


def _ema_scalar_timeline(
    normalized: np.ndarray,
    total: int,
    n_bus: int,
    *,
    smoothing: float,
) -> np.ndarray:
    history = np.zeros(max(total, 0), dtype=np.float32)
    if total <= 0 or normalized.size == 0:
        return history
    s = float(smoothing)
    one_minus_s = 1.0 - s
    acc = 0.0
    for f in range(total):
        if f < n_bus:
            acc = acc * s + float(normalized[f]) * one_minus_s
        else:
            acc *= s
        history[f] = acc
    return history


def precompute_bus_drives(
    frames: list[AudioBusFrame] | None,
    total: int,
    *,
    smoothing: float = DEFAULT_BASS_SMOOTHING,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Job-normalized, EMA-smoothed bass/mid/high/amplitude timelines."""
    empty = np.zeros(max(total, 0), dtype=np.float32)
    if total <= 0 or not frames:
        return empty, empty.copy(), empty.copy(), empty.copy()

    n_bus = min(total, len(frames))
    bass_norm = normalize_bus_scalar(
        np.asarray([float(frames[f].bass) for f in range(n_bus)], dtype=np.float32)
    )
    mid_norm = normalize_bus_scalar(
        np.asarray([float(frames[f].mid) for f in range(n_bus)], dtype=np.float32)
    )
    high_norm = normalize_bus_scalar(
        np.asarray([float(frames[f].high) for f in range(n_bus)], dtype=np.float32)
    )
    amp_norm = normalize_bus_scalar(
        np.asarray([float(frames[f].amplitude) for f in range(n_bus)], dtype=np.float32)
    )
    kw = {"smoothing": smoothing}
    return (
        _ema_scalar_timeline(bass_norm, total, n_bus, **kw),
        _ema_scalar_timeline(mid_norm, total, n_bus, **kw),
        _ema_scalar_timeline(high_norm, total, n_bus, **kw),
        _ema_scalar_timeline(amp_norm, total, n_bus, **kw),
    )


def spin_angle_rad(
    time_s: float, spin_speed_deg: float, spin_bass_deg: float, bass: float
) -> float:
    """Stateless turntable angle: constant spin plus optional bass boost to speed."""
    speed_deg = spin_speed_deg + spin_bass_deg * bass
    return np.radians(speed_deg) * time_s


def mat4_perspective(fov_deg: float, aspect: float, near: float, far: float) -> np.ndarray:
    f = 1.0 / float(np.tan(np.radians(fov_deg) * 0.5))
    m = np.zeros((4, 4), dtype=np.float32)
    m[0, 0] = f / aspect
    m[1, 1] = f
    m[2, 2] = (far + near) / (near - far)
    m[2, 3] = 2.0 * far * near / (near - far)
    m[3, 2] = -1.0
    return m


def spherical_unit_direction(
    azimuth_deg: float, elevation_deg: float
) -> tuple[float, float, float]:
    """Unit vector from mesh origin toward a point on the unit sphere (world space)."""
    az = float(np.radians(azimuth_deg))
    el = float(np.radians(elevation_deg))
    return (
        float(np.cos(el) * np.sin(az)),
        float(np.sin(el)),
        float(np.cos(el) * np.cos(az)),
    )


def mesh_camera_view(
    camera_distance: float,
    camera_azimuth_deg: float,
    camera_elevation_deg: float,
    zoom: float = 1.0,
) -> np.ndarray:
    dist = max(camera_distance, 1e-6) / max(zoom, 1e-6)
    az = float(np.radians(camera_azimuth_deg))
    el = float(np.radians(camera_elevation_deg))
    eye = (
        float(dist * np.cos(el) * np.sin(az)),
        float(dist * np.sin(el)),
        float(dist * np.cos(el) * np.cos(az)),
    )
    up = (
        (float(np.sin(az + np.pi / 2)), 0.0, float(np.cos(az + np.pi / 2)))
        if abs(camera_elevation_deg) > 88.0
        else (0.0, 1.0, 0.0)
    )
    return mat4_look_at(eye=eye, target=(0.0, 0.0, 0.0), up=up)


def light_dir_in_eye_space(
    view: np.ndarray,
    light_azimuth_deg: float,
    light_elevation_deg: float,
) -> tuple[float, float, float]:
    """World-absolute light direction, rotated into eye space (spin-independent)."""
    world = np.array(
        spherical_unit_direction(light_azimuth_deg, light_elevation_deg), dtype=np.float32
    )
    eye = view[:3, :3] @ world
    n = max(float(np.linalg.norm(eye)), 1e-8)
    return (float(eye[0] / n), float(eye[1] / n), float(eye[2] / n))


def mesh_mvp_perspective(
    aspect: float,
    camera_distance: float,
    camera_azimuth_deg: float,
    camera_elevation_deg: float,
    fov_deg: float,
    spin_y_rad: float,
    zoom: float = 1.0,
    *,
    offset_y: float = 0.5,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    view = mesh_camera_view(camera_distance, camera_azimuth_deg, camera_elevation_deg, zoom)
    proj = mat4_perspective(fov_deg, aspect, near=0.01, far=200.0)
    # Screen-space Y shift: proj[1,2] offset gives constant NDC_y translation post-divide.
    proj[1, 2] = (offset_y - 0.5) * 2.0
    model = mat4_rotate_y(spin_y_rad)
    model_view = view @ model
    return proj @ model_view, model_view, view


def apply_clip_scissor(
    gl: moderngl.Context, bounds: Rect, canvas_h: float
) -> tuple[int, int, int, int]:
    """Clip and remap NDC to the clip bounds. Returns the previous viewport.

    Pass the returned viewport to :func:`restore_clip_scissor` after drawing —
    the FBO is shared across all GL clips in a track, and a leaked viewport
    squeezes every later clip into this clip layout band.
    """
    prev_viewport = gl.viewport
    sc = (
        int(bounds.x),
        int(canvas_h - bounds.y - bounds.height),
        max(int(bounds.width), 1),
        max(int(bounds.height), 1),
    )
    gl.scissor = sc
    gl.viewport = sc
    return prev_viewport


def restore_clip_scissor(gl: moderngl.Context, prev_viewport: tuple[int, int, int, int]) -> None:
    gl.scissor = None
    gl.viewport = prev_viewport


def draw_mesh_blend(gl: moderngl.Context, vao: moderngl.VertexArray) -> None:
    """Alpha-blend mesh over prior GL clips (same model as Bars / Tunnel). No depth test."""
    gl.disable(moderngl.DEPTH_TEST)
    vao.render()


def draw_mesh_3d(gl: moderngl.Context, vao: moderngl.VertexArray) -> None:
    """Render a 3D mesh with depth test and back-face culling, then restore 2D state."""
    gl.enable(moderngl.DEPTH_TEST)
    gl.enable(moderngl.CULL_FACE)
    vao.render()
    gl.disable(moderngl.DEPTH_TEST)
    gl.disable(moderngl.CULL_FACE)


def mat4_look_at(
    eye: tuple[float, float, float],
    target: tuple[float, float, float],
    up: tuple[float, float, float],
) -> np.ndarray:
    eye_v = np.array(eye, dtype=np.float32)
    target_v = np.array(target, dtype=np.float32)
    up_v = np.array(up, dtype=np.float32)
    f = target_v - eye_v
    f = f / max(np.linalg.norm(f), 1e-8)
    s = np.cross(f, up_v)
    s = s / max(np.linalg.norm(s), 1e-8)
    u = np.cross(s, f)
    m = np.identity(4, dtype=np.float32)
    m[0, :3] = s
    m[1, :3] = u
    m[2, :3] = -f
    m[0, 3] = -np.dot(s, eye_v)
    m[1, 3] = -np.dot(u, eye_v)
    m[2, 3] = np.dot(f, eye_v)
    return m


def mat4_rotate_y(angle_rad: float) -> np.ndarray:
    c = float(np.cos(angle_rad))
    s = float(np.sin(angle_rad))
    m = np.identity(4, dtype=np.float32)
    m[0, 0] = c
    m[0, 2] = s
    m[2, 0] = -s
    m[2, 2] = c
    return m
