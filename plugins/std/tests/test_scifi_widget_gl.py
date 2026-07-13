"""Tests for std-scifi-widget-gl registration, presets, and audio drive."""

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
from pixfabrica_std.background.scifi_widget_gl import (
    _QUAD,
    _VERT,
    _WIDGET_ANCHOR_OFFSET,
    _WIDGET_KIND_IDS,
    SciFiWidgetGL,
    _frag_for_widget_kind,
)


def _set_uniform(prog: moderngl.Program, name: str, value: Any) -> None:
    if name not in prog:
        return
    cast(moderngl.Uniform, prog[name]).value = value


def test_clip_type_registered() -> None:
    assert SciFiWidgetGL.clip_type == "std-scifi-widget-gl"


def test_widget_kind_catalog() -> None:
    assert len(_WIDGET_KIND_IDS) == 9
    assert len(_WIDGET_ANCHOR_OFFSET) == 9
    assert _WIDGET_KIND_IDS["circle_dial"] == 1
    clip = SciFiWidgetGL(id="n1")
    assert clip.widget == "circle_dial"


def test_shader_compiles() -> None:
    ctx = moderngl.create_standalone_context()
    for elem_id in range(9):
        ctx.program(vertex_shader=_VERT, fragment_shader=_frag_for_widget_kind(elem_id))


def test_anchor_correction_centers_widgets() -> None:
    res = 256
    ctx = moderngl.create_standalone_context()

    for elem_name, elem_id in _WIDGET_KIND_IDS.items():
        prog = ctx.program(vertex_shader=_VERT, fragment_shader=_frag_for_widget_kind(elem_id))
        vbo = ctx.buffer(_QUAD.tobytes())
        vao = ctx.simple_vertex_array(prog, vbo, "in_vert")
        for name, val in [
            ("u_res", (res, res)),
            ("u_origin", (0.0, 0.0)),
            ("u_canvas_h", float(res)),
            ("u_anim_t", 0.0),
            ("u_bound_r", 0.0),
            ("u_color", (1.0, 1.0, 1.0)),
            ("u_offset_x", 0.5),
            ("u_offset_y", 0.5),
            ("u_scale", 1.0),
            ("u_angle", 0.0),
            ("u_brightness", 1.0),
            ("u_luma_alpha", 0.0),
            ("u_opacity", 1.0),
        ]:
            _set_uniform(prog, name, val)

        fbo = ctx.framebuffer(color_attachments=[ctx.texture((res, res), 4)])
        fbo.use()
        fbo.clear(0.0, 0.0, 0.0, 0.0)
        vao.render()

        data = np.frombuffer(fbo.read(components=4), dtype=np.uint8).reshape(res, res, 4)
        mask = data[:, :, 3] > 5
        if not mask.any():
            continue

        ys, xs = np.where(mask)
        cx = (xs.min() + xs.max()) / 2.0
        cy = (ys.min() + ys.max()) / 2.0
        uv_x = (cx * 2.0 - res) / res
        uv_y = -((cy * 2.0 - res) / res)
        assert abs(uv_x) < 0.02, elem_name
        assert abs(uv_y) < 0.02, elem_name


def test_anchor_left_at_widescreen() -> None:
    res_w, res_h = 1920, 1080
    ctx = moderngl.create_standalone_context()
    elem_id = _WIDGET_KIND_IDS["circle_dial"]
    prog = ctx.program(vertex_shader=_VERT, fragment_shader=_frag_for_widget_kind(elem_id))
    vbo = ctx.buffer(_QUAD.tobytes())
    vao = ctx.simple_vertex_array(prog, vbo, "in_vert")
    for name, val in [
        ("u_res", (res_w, res_h)),
        ("u_origin", (0.0, 0.0)),
        ("u_canvas_h", float(res_h)),
        ("u_anim_t", 0.0),
        ("u_bound_r", 0.0),
        ("u_color", (1.0, 1.0, 1.0)),
        ("u_offset_x", 0.0),
        ("u_offset_y", 0.5),
        ("u_scale", 1.0),
        ("u_angle", 0.0),
        ("u_brightness", 1.0),
        ("u_luma_alpha", 0.0),
        ("u_opacity", 1.0),
    ]:
        _set_uniform(prog, name, val)

    fbo = ctx.framebuffer(color_attachments=[ctx.texture((res_w, res_h), 4)])
    fbo.use()
    fbo.clear(0.0, 0.0, 0.0, 0.0)
    vao.render()

    data = np.frombuffer(fbo.read(components=4), dtype=np.uint8).reshape(res_h, res_w, 4)
    mask = data[:, :, 3] > 5
    assert mask.any()
    xs = np.where(mask)[1]
    assert xs.min() < res_w * 0.02, xs.min()


def test_presets() -> None:
    presets = {p["id"]: p for p in SciFiWidgetGL.clip_presets}
    assert presets["center_dial"]["values"]["widget"] == "circle_dial"
    assert presets["corner_slider"]["values"]["widget"] == "slider"
    assert presets["corner_slider"]["values"]["offset_x"] == 0.88
    assert presets["corner_slider"]["values"]["offset_y"] == 0.92


def _prepare_ctx(
    tmp_path: Path,
    *,
    audio: dict,
    duration_sec: float = 8.0,
) -> PrepareContext:
    ji = JobInfo(
        title="t",
        description="d",
        width=640,
        height=480,
        fps=30.0,
        duration=duration_sec,
        colors=ColorPalette(),
        typography=FontPalette(),
        locale="en",
    )
    td = tmp_path / "temp"
    cd = tmp_path / "cache"
    td.mkdir(exist_ok=True)
    cd.mkdir(exist_ok=True)
    return PrepareContext(job=ji, temp_dir=td, cache_dir=cd, audio=audio)


def test_amp_history_uses_job_wide_range(tmp_path: Path) -> None:
    frames = [
        AudioBusFrame(
            spectrum=[0.0] * N_SPECTRUM,
            bass=0.0,
            mid=0.0,
            high=0.0,
            beat=False,
            amplitude=0.02,
        ),
        AudioBusFrame(
            spectrum=[0.0] * N_SPECTRUM,
            bass=0.0,
            mid=0.0,
            high=0.0,
            beat=True,
            amplitude=0.9,
        ),
    ]
    clip = SciFiWidgetGL(id="sw", bus_select="main", sensitivity=2.0)
    ctx = _prepare_ctx(tmp_path, audio={"main": frames}, duration_sec=2 / 30.0)
    asyncio.run(clip.prepare(ctx))

    amp = clip._amp_history  # noqa: SLF001
    assert amp[1] > amp[0]
    assert amp[1] > 0.5


def test_stem_analyzer_drums_has_visible_amp_swing(tmp_path: Path) -> None:
    from pixfabrica_core.audio.analysis import StemAnalyzer

    audio = Path("web/public/preview-samples/sources/drums.mp3")
    if not audio.exists():
        pytest.skip("preview sample missing")

    tl = StemAnalyzer().analyze(audio, 0.0, 8.0, 30.0)
    clip = SciFiWidgetGL(id="sw", bus_select="main", sensitivity=2.5)
    ctx = _prepare_ctx(tmp_path, audio={"main": tl})
    asyncio.run(clip.prepare(ctx))

    amp = clip._amp_history  # noqa: SLF001
    assert float(np.percentile(amp, 95)) > 0.5
    assert float(np.std(amp)) > 0.1
