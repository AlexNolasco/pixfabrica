from __future__ import annotations

import asyncio
import logging
from typing import ClassVar

import moderngl
import numpy as np
from pydantic import Field, PrivateAttr

from pixfabrica_core.audio.mixin import AudioVisualMixin
from pixfabrica_core.clips import ClipCategory, ClipGL, ClipTag, PrepareContext, RenderContext
from pixfabrica_core.graphics import Rect
from pixfabrica_core.theme.color import Color, ColorToken, color_field, resolve_color
from pixfabrica_std.mesh.gltf_loader import (
    MESH_ASSET_FILES,
    MeshAsset,
    bundled_glb_path,
    interleave_pos_norm,
    load_glb_triangles,
    normalize_mesh,
)
from pixfabrica_std.mesh.shader_helper import (
    DEFAULT_CAMERA_DISTANCE,
    LAMBERT_MESH_FRAG,
    LAMBERT_MESH_VERT,
    apply_clip_scissor,
    bass_zoom,
    draw_mesh_3d,
    light_dir_in_eye_space,
    mesh_mvp_perspective,
    precompute_bass_drive,
    restore_clip_scissor,
    set_uniform,
    spin_angle_rad,
    upload_indexed_mesh,
    write_mvp,
    write_normal_matrix,
)

log = logging.getLogger("pixfabrica.std.mesh")


class GltfMeshGL(AudioVisualMixin, ClipGL):
    """glTF mesh — orthographic front view, Lambert shading, spin, optional bass zoom."""

    clip_type: ClassVar[str] = "std-gltf-mesh"
    clip_category: ClassVar[ClipCategory] = ClipCategory.MESH
    clip_tags: ClassVar[list[str]] = [ClipTag.GL, ClipTag.AUDIO_REACTIVE]

    mesh: MeshAsset = Field(
        default="skull",
        description="Bundled glTF asset to load from plugin resources",
    )
    mesh_color: ColorToken | Color = color_field(ColorToken.PRIMARY)
    light_color: ColorToken | Color = color_field(ColorToken.PRIMARY, default=Color("#ffffff"))
    light_azimuth: float = Field(
        default=0.0,
        ge=0.0,
        le=360.0,
        multiple_of=1.0,
        description="Light horizontal angle (0 = front, 90 = right, 180 = back, 270 = left)",
    )
    light_elevation: float = Field(
        default=-90.0,
        ge=-89.0,
        le=89.0,
        multiple_of=1.0,
        description="Light vertical angle (0 = eye-level, positive = above, negative = below)",
    )
    offset_y: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Vertical placement of mesh origin as fraction of clip height (0=top, 0.5=center, 1=bottom)",
    )
    opacity: float = Field(default=1.0, ge=0.0, le=1.0, description="Overall layer opacity")
    camera_distance: float = Field(
        default=DEFAULT_CAMERA_DISTANCE,
        ge=0.0,
        le=20.0,
        multiple_of=0.1,
        description="Eye-to-mesh distance (larger = farther / smaller on screen)",
    )
    camera_azimuth: float = Field(
        default=0.0,
        ge=0.0,
        le=360.0,
        multiple_of=1.0,
        description="Camera horizontal angle (0 = front, 90 = right, 180 = back, 270 = left)",
    )
    camera_elevation: float = Field(
        default=0.0,
        ge=-89.0,
        le=89.0,
        multiple_of=1.0,
        description="Camera vertical angle (0 = eye-level, positive = above, negative = below)",
    )
    camera_fov: float = Field(
        default=45.0,
        ge=20.0,
        le=90.0,
        multiple_of=1.0,
        description="Perspective field of view in degrees (lower = telephoto, higher = wide)",
    )
    sensitivity: float = Field(
        default=0.3,
        ge=0.0,
        le=2.0,
        multiple_of=0.1,
        description="Perspective zoom-in at full bass when bus_select is set (0 = no audio zoom)",
    )
    spin_speed: float = Field(
        ge=0.0,
        le=32.0,
        multiple_of=1.0,
        default=18.0,
        description="Continuous Y-axis spin in degrees per second (0 = no idle spin)",
    )
    spin_bass: float = Field(
        default=0,
        ge=0.0,
        le=16.0,
        multiple_of=1.0,
        description="Extra degrees per second at full bass when bus_select is set (stacks on spin_speed)",
    )
    ambient: float = Field(
        default=0.25,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Ambient term in Lambert shading",
    )

    _program: moderngl.Program | None = PrivateAttr(default=None)
    _vao: moderngl.VertexArray | None = PrivateAttr(default=None)
    _mesh_interleaved: np.ndarray = PrivateAttr(
        default_factory=lambda: np.zeros(0, dtype=np.float32)
    )
    _indices: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype=np.uint32))
    _canvas_h: float = PrivateAttr(default=0.0)
    _gl_ready: bool = PrivateAttr(default=False)
    _prepared_mesh: MeshAsset | None = PrivateAttr(default=None)
    _bass_history: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype="f4"))

    async def prepare(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        await asyncio.to_thread(self._prepare_sync, ctx)

    def _prepare_sync(self, ctx: PrepareContext) -> None:
        self._canvas_h = float(ctx.job.height)
        total = max(ctx.job.total_frames, 0)
        self._bass_history = precompute_bass_drive(self.bus_timeline(ctx), total)
        if self._prepared_mesh == self.mesh and self._mesh_interleaved.size > 0:
            return
        path = bundled_glb_path(MESH_ASSET_FILES[self.mesh])
        positions, normals, indices = load_glb_triangles(path)
        positions, normals = normalize_mesh(positions, normals)
        self._mesh_interleaved = interleave_pos_norm(positions, normals)
        self._indices = indices.astype(np.uint32)
        self._prepared_mesh = self.mesh
        self._gl_ready = False
        self._program = None
        self._vao = None

    def draw(self, ctx: RenderContext) -> None:
        gl: moderngl.Context = ctx.canvas
        b = ctx.bounds

        if not self._gl_ready:
            self._upload_gl(gl)

        prog = self._program
        assert prog is not None and self._vao is not None

        aspect = max(float(b.width), 1.0) / max(float(b.height), 1.0)
        bus_active = self.bus_active_for_draw(ctx)
        bass = self._bass_for_frame(ctx)
        zoom = bass_zoom(bus_active, self.sensitivity, bass)
        angle = spin_angle_rad(ctx.time.t, self.spin_speed, self.spin_bass, bass)
        mvp, model_view, view = mesh_mvp_perspective(
            aspect,
            float(self.camera_distance),
            float(self.camera_azimuth),
            float(self.camera_elevation),
            float(self.camera_fov),
            angle,
            zoom,
            offset_y=float(self.offset_y),
        )
        light_dir = light_dir_in_eye_space(
            view, float(self.light_azimuth), float(self.light_elevation)
        )

        mr, mg, mb, _ = resolve_color(self.mesh_color, ctx.job.colors).rgba
        lr, lg, lb, _ = resolve_color(self.light_color, ctx.job.colors).rgba

        write_mvp(prog, mvp)
        write_normal_matrix(prog, model_view)
        set_uniform(prog, "u_mesh_color", (mr, mg, mb))
        set_uniform(prog, "u_light_color", (lr, lg, lb))
        set_uniform(prog, "u_light_dir", light_dir)
        set_uniform(prog, "u_ambient", float(self.ambient))
        set_uniform(prog, "u_opacity", float(self.opacity))

        prev_viewport = apply_clip_scissor(gl, b, self._canvas_h)
        draw_mesh_3d(gl, self._vao)
        restore_clip_scissor(gl, prev_viewport)

    def _upload_gl(self, gl: moderngl.Context) -> None:
        self._program = gl.program(
            vertex_shader=LAMBERT_MESH_VERT, fragment_shader=LAMBERT_MESH_FRAG
        )
        self._vao = upload_indexed_mesh(gl, self._program, self._mesh_interleaved, self._indices)
        self._gl_ready = True

    def _bass_for_frame(self, ctx: RenderContext) -> float:
        if not self.bus_active_for_draw(ctx):
            return 0.0
        if self._bass_history.shape[0] > 0:
            f = max(0, min(ctx.time.frame, self._bass_history.shape[0] - 1))
            return float(self._bass_history[f])
        return float(np.clip(ctx.audio_bus_frame.bass, 0.0, 1.0))
