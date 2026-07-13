"""Mesh clips must not leak viewport/scissor state into the shared track FBO.

Regression for: in a vertical/horizontal track layout, a mesh clip left the
GL viewport set to its own band, squeezing every other GL clip in the track
into that band (effectively invisible).
"""

from __future__ import annotations

import asyncio

import moderngl
import pytest

from pixfabrica_core.clips import JobInfo, PrepareContext, RenderContext, TimeState
from pixfabrica_core.graphics import Rect
from pixfabrica_core.theme.color import ColorPalette
from pixfabrica_core.theme.typography import FontPalette
from pixfabrica_std.mesh.gltf_mesh_gl import GltfMeshGL
from pixfabrica_std.mesh.shader_helper import apply_clip_scissor, restore_clip_scissor

W, H = 160, 120


@pytest.fixture(scope="module")
def gl() -> moderngl.Context:
    ctx = moderngl.create_standalone_context()
    ctx.enable(moderngl.BLEND)
    return ctx


@pytest.fixture(scope="module")
def fbo(gl: moderngl.Context) -> moderngl.Framebuffer:
    return gl.framebuffer(
        color_attachments=[gl.texture((W, H), 4)],
        depth_attachment=gl.depth_renderbuffer((W, H)),
    )


def _job() -> JobInfo:
    return JobInfo(
        title="t",
        description="d",
        width=W,
        height=H,
        fps=30.0,
        duration=5.0,
        colors=ColorPalette(),
        typography=FontPalette(),
        locale="en",
    )


def test_apply_clip_scissor_round_trips_viewport(
    gl: moderngl.Context, fbo: moderngl.Framebuffer
) -> None:
    fbo.use()
    gl.viewport = (0, 0, W, H)
    band = Rect(0, 0, W, H / 2)

    prev = apply_clip_scissor(gl, band, float(H))
    assert prev == (0, 0, W, H)
    assert tuple(gl.viewport) == (0, H // 2, W, H // 2)

    restore_clip_scissor(gl, prev)
    assert tuple(gl.viewport) == (0, 0, W, H)


def test_gltf_mesh_draw_leaves_viewport_intact(
    gl: moderngl.Context, fbo: moderngl.Framebuffer
) -> None:
    clip = GltfMeshGL(id="mesh1")
    asyncio.run(clip.prepare(PrepareContext.from_env(_job())))

    fbo.use()
    gl.viewport = (0, 0, W, H)
    ctx = RenderContext(
        job=_job(),
        time=TimeState(frame=0, t=0.0),
        bounds=Rect(0, H / 2, W, H / 2),  # bottom band of a vertical layout
        canvas=gl,
    )
    clip.draw(ctx)

    assert tuple(gl.viewport) == (0, 0, W, H)
