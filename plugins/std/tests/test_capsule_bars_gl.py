"""Tests for std-capsule-bars-gl shader, symmetry, and bar-count coercion."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, cast

import moderngl
import numpy as np
import pytest

from pixfabrica_core.audio.bus import N_SPECTRUM, AudioBusFrame
from pixfabrica_core.clips import JobInfo, PrepareContext
from pixfabrica_core.theme.color import ColorPalette
from pixfabrica_core.theme.typography import FontPalette
from pixfabrica_std.audio.capsule_bars_gl import (
    _FLUTTER_AMP,
    _FRAG,
    _MAX_BARS,
    _MIN_HEIGHT_FRAC,
    _PULSE_AMP,
    _QUAD,
    _RIPPLE_AMP,
    _VERT,
    CapsuleBarsGL,
    _bus_band_drives,
)


def _set_uniform(prog: moderngl.Program, name: str, value: Any) -> None:
    if name not in prog:
        return
    cast(moderngl.Uniform, prog[name]).value = value


def _prepare_ctx(
    tmp_path: Path,
    *,
    fps: float = 30.0,
    duration_sec: float = 2.0,
    audio: dict | None = None,
) -> PrepareContext:
    ji = JobInfo(
        title="t",
        description="d",
        width=640,
        height=480,
        fps=fps,
        duration=duration_sec,
        colors=ColorPalette(),
        typography=FontPalette(),
        locale="en",
    )
    td = tmp_path / "temp"
    cd = tmp_path / "cache"
    td.mkdir(exist_ok=True)
    cd.mkdir(exist_ok=True)
    return PrepareContext(job=ji, temp_dir=td, cache_dir=cd, audio=audio or {})


def test_clip_type_registered() -> None:
    assert CapsuleBarsGL.clip_type == "std-capsule-bars-gl"


@pytest.mark.parametrize("even, expected", [(4, 5), (6, 7), (8, 7)])
def test_bar_count_coerced_to_odd(even: int, expected: int) -> None:
    clip = CapsuleBarsGL(id="n", bar_count=even)
    assert clip.bar_count == expected


def test_shader_compiles() -> None:
    ctx = moderngl.create_standalone_context()
    ctx.program(vertex_shader=_VERT, fragment_shader=_FRAG)


def test_precompute_symmetric_heights(tmp_path: Path) -> None:
    clip = CapsuleBarsGL(id="n", bar_count=7)
    pctx = _prepare_ctx(tmp_path, duration_sec=1 / 30.0)
    asyncio.run(clip.prepare(pctx))

    row = clip._bar_history[0]  # noqa: SLF001
    heights = row[:7]
    assert np.isclose(heights[0], heights[6])
    assert np.isclose(heights[1], heights[5])
    assert np.isclose(heights[2], heights[4])
    assert heights[3] >= heights[2]
    assert heights[3] >= heights[0]


def test_idle_pulse_modulates_over_time(tmp_path: Path) -> None:
    clip = CapsuleBarsGL(id="n", bar_count=7)
    fps = 30.0
    pctx = _prepare_ctx(tmp_path, fps=fps, duration_sec=6.0)
    asyncio.run(clip.prepare(pctx))

    center = clip._bar_history[:, 3]  # noqa: SLF001
    assert center.max() - center.min() > (_PULSE_AMP + _RIPPLE_AMP + _FLUTTER_AMP) * 0.2


def test_speed_increases_motion_rate(tmp_path: Path) -> None:
    slow = CapsuleBarsGL(id="slow", bar_count=7, speed=0.5)
    fast = CapsuleBarsGL(id="fast", bar_count=7, speed=3.0)
    pctx = _prepare_ctx(tmp_path, fps=30.0, duration_sec=3.0)
    asyncio.run(slow.prepare(pctx))
    fast_dir = tmp_path / "fast"
    fast_dir.mkdir(exist_ok=True)
    asyncio.run(fast.prepare(_prepare_ctx(fast_dir, fps=30.0, duration_sec=3.0)))

    slow_crossings = np.sum(np.diff(np.sign(np.diff(slow._bar_history[:, 3]))) != 0)  # noqa: SLF001
    fast_crossings = np.sum(np.diff(np.sign(np.diff(fast._bar_history[:, 3]))) != 0)  # noqa: SLF001
    assert fast_crossings > slow_crossings


def test_center_tallest_each_frame(tmp_path: Path) -> None:
    clip = CapsuleBarsGL(id="n", bar_count=7)
    pctx = _prepare_ctx(tmp_path, fps=30.0, duration_sec=4.0)
    asyncio.run(clip.prepare(pctx))

    for row in clip._bar_history:  # noqa: SLF001
        heights = row[:7]
        assert heights[3] > max(heights[i] for i in range(7) if i != 3)


def test_bus_band_drives_returns_per_band() -> None:
    frame = AudioBusFrame(
        spectrum=[0.0] * N_SPECTRUM,
        bass=0.64,
        mid=0.5,
        high=0.2,
        beat=False,
        amplitude=0.04,
    )
    bass, mid, high = _bus_band_drives(frame)
    assert bass > mid > high
    assert 0.0 < high <= 1.0


def test_bus_drives_bar_heights_per_band(tmp_path: Path) -> None:
    frames = [
        AudioBusFrame(
            spectrum=[0.0] * N_SPECTRUM,
            bass=0.9,
            mid=0.3,
            high=0.1,
            beat=False,
            amplitude=0.12,
        )
        for _ in range(30)
    ]
    clip = CapsuleBarsGL(id="n", bar_count=5, bus_select="main", smoothing=0.0)
    pctx = _prepare_ctx(tmp_path, duration_sec=1.0, audio={"main": frames})
    asyncio.run(clip.prepare(pctx))

    assert clip._drive_history.shape == (30, 3)  # noqa: SLF001

    band_drives = clip._drive_history[29]  # noqa: SLF001
    heights = clip._bus_bar_heights(band_drives, 1.0, 5)  # noqa: SLF001
    # center (distance 0, bass) should be tallest; mirrored pairs equal
    assert heights[2] > heights[1]
    assert heights[2] > heights[0]
    assert np.isclose(heights[0], heights[4])
    assert np.isclose(heights[1], heights[3])


def test_bus_floor_keeps_bars_visible(tmp_path: Path) -> None:
    frames = [
        AudioBusFrame(
            spectrum=[0.0] * N_SPECTRUM,
            bass=0.0,
            mid=0.0,
            high=0.0,
            beat=False,
            amplitude=0.0,
        )
        for _ in range(10)
    ]
    clip = CapsuleBarsGL(id="n", bar_count=3, bus_select="main", smoothing=0.0)
    pctx = _prepare_ctx(tmp_path, duration_sec=10 / 30.0, audio={"main": frames})
    asyncio.run(clip.prepare(pctx))

    band_drives = clip._drive_history[9]  # noqa: SLF001
    heights = clip._bus_bar_heights(band_drives, 0.0, 3)  # noqa: SLF001
    # floor = _MIN_HEIGHT_FRAC * silhouette — all bars must remain visible
    assert heights[:3].min() >= _MIN_HEIGHT_FRAC * clip._silhouettes.min() * 0.99  # noqa: SLF001


def test_shader_renders_centered_cluster() -> None:
    res = 256
    ctx = moderngl.create_standalone_context()
    prog = ctx.program(vertex_shader=_VERT, fragment_shader=_FRAG)
    vbo = ctx.buffer(_QUAD.tobytes())
    vao = ctx.simple_vertex_array(prog, vbo, "in_vert")

    heights = (0.55, 0.92, 0.78, 1.0, 0.78, 0.92, 0.55)
    for name, val in [
        ("u_res", (res, res)),
        ("u_origin", (0.0, 0.0)),
        ("u_canvas_h", float(res)),
        ("u_offset_x", 0.5),
        ("u_offset_y", 0.5),
        ("u_scale", 1.0),
        ("u_angle", 0.0),
        ("u_bar_count_f", 7.0),
        ("u_bar_gap_ratio", 0.22),
        ("u_max_height", 0.65),
        ("u_cluster_half_w", 0.5),
        ("u_color_tl", (1.0, 0.5, 0.0)),
        ("u_color_tr", (0.0, 1.0, 0.2)),
        ("u_color_bl", (1.0, 0.0, 0.8)),
        ("u_color_br", (0.1, 0.2, 1.0)),
        ("u_glow_intensity", 0.0),
        ("u_bar_heights", heights),
    ]:
        _set_uniform(prog, name, val)

    fbo = ctx.framebuffer(color_attachments=[ctx.texture((res, res), 4)])
    fbo.use()
    fbo.clear(0.0, 0.0, 0.0, 0.0)
    vao.render()

    data = np.frombuffer(fbo.read(components=4), dtype=np.uint8).reshape(res, res, 4)
    mask = data[:, :, 3] > 10
    assert mask.any()
    ys, xs = np.where(mask)
    cx = (xs.min() + xs.max()) / 2.0
    cy = (ys.min() + ys.max()) / 2.0
    assert abs(cx - res / 2) < 8
    assert abs(cy - res / 2) < 8


def test_bus_center_tallest_each_frame(tmp_path: Path) -> None:
    frames = [
        AudioBusFrame(
            spectrum=[0.0] * N_SPECTRUM,
            bass=0.05,
            mid=0.95,
            high=0.8,
            beat=False,
            amplitude=0.7,
        )
        for _ in range(20)
    ]
    clip = CapsuleBarsGL(id="n", bar_count=5, bus_select="main", smoothing=0.0)
    pctx = _prepare_ctx(tmp_path, duration_sec=20 / 30.0, audio={"main": frames})
    asyncio.run(clip.prepare(pctx))

    center = clip.bar_count // 2
    for f in range(clip._drive_history.shape[0]):  # noqa: SLF001
        band_drives = clip._drive_history[f]  # noqa: SLF001
        amp = float(clip._amp_history[f])  # noqa: SLF001
        heights = clip._bus_bar_heights(band_drives, amp, clip.bar_count)  # noqa: SLF001
        row = heights[: clip.bar_count]
        assert row[center] >= max(row[i] for i in range(clip.bar_count) if i != center)


def test_bus_drives_normalize_with_stem_analyzer(tmp_path: Path) -> None:
    """StemAnalyzer bass/mid/high should span a usable drive range after job-wide norm."""
    from pixfabrica_core.audio.analysis import StemAnalyzer

    audio = Path("web/public/preview-samples/sources/drums.mp3")
    if not audio.exists():
        pytest.skip("preview sample missing")

    fps = 30.0
    duration = 8.0

    tl = StemAnalyzer().analyze(audio, 0.0, duration, fps)
    clip = CapsuleBarsGL(id="n", bar_count=5, bus_select="main", smoothing=0.45, sensitivity=2.5)
    pctx = _prepare_ctx(tmp_path, duration_sec=duration, audio={"main": tl})
    asyncio.run(clip.prepare(pctx))
    center = clip.bar_count // 2
    for f in range(clip._drive_history.shape[0]):  # noqa: SLF001
        heights = clip._bus_bar_heights(  # noqa: SLF001
            clip._drive_history[f],
            float(clip._amp_history[f]),
            clip.bar_count,
        )
        row = heights[: clip.bar_count]
        assert row[center] >= max(row[i] for i in range(clip.bar_count) if i != center)

    drives = clip._drive_history[:, 0]  # noqa: SLF001
    p5, p95 = np.percentile(drives, [5, 95])
    assert float(p95 - p5) > 0.2


def test_default_bar_count_is_three() -> None:
    clip = CapsuleBarsGL(id="n")
    assert clip.bar_count == 3


def test_glow_intensity_defaults_off() -> None:
    clip = CapsuleBarsGL(id="n")
    assert clip.glow_intensity == 0.0


def test_max_bars_constant_matches_shader() -> None:
    assert _MAX_BARS == 7
