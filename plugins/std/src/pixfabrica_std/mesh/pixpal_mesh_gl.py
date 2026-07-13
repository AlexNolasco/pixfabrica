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
from pixfabrica_core.prepare_diagnostics import record_prepare_asset_failure
from pixfabrica_std.mesh.gltf_loader import (
    interleave_pos_norm_uv,
    load_glb_mesh,
    normalize_mesh,
    resolve_mesh_path,
)
from pixfabrica_std.mesh.pixpal_shader import (
    PIXPAL_FRAG,
    PIXPAL_VERT,
    bind_pixpal_textures,
    load_pixpal_textures,
    upload_pixpal_mesh,
    write_pixpal_uniforms,
)
from pixfabrica_std.mesh.shader_helper import (
    DEFAULT_CAMERA_DISTANCE,
    apply_clip_scissor,
    bass_zoom,
    draw_mesh_3d,
    light_dir_in_eye_space,
    mesh_mvp_perspective,
    precompute_bass_drive,
    restore_clip_scissor,
    spin_angle_rad,
)

log = logging.getLogger("pixfabrica.std.mesh.pixpal")

_DEFAULT_MESH_FILE = "cube_imphenzia.glb"
_MAX_TRIANGLES = 10_000


class PixPalMeshGL(AudioVisualMixin, ClipGL):
    """Imphenzia PixPal mesh — palette textures, UV scroll animation, path to .glb."""

    clip_type: ClassVar[str] = "std-pixpal-mesh"
    clip_category: ClassVar[ClipCategory] = ClipCategory.MESH
    clip_tags: ClassVar[list[str]] = [ClipTag.GL, ClipTag.AUDIO_REACTIVE]

    source: str = Field(
        default="",
        description=(
            "Absolute path to a PixPal-authored .glb. Leave empty to use the bundled "
            "cube_imphenzia.glb."
        ),
    )
    offset_y: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Vertical placement (0=top, 0.5=center, 1=bottom)",
    )
    opacity: float = Field(default=1.0, ge=0.0, le=1.0, description="Overall layer opacity")
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
        description="Orthographic zoom-in at full bass when bus_select is set",
    )
    emissive_factor: float = Field(
        default=5.0,
        ge=0.0,
        le=32.0,
        multiple_of=0.5,
        description="Emission map multiplier (Babylon demo uses ~5)",
    )
    emissive_sensitivity: float = Field(
        default=0.75,
        ge=0.0,
        le=4.0,
        multiple_of=0.1,
        description="Extra emissive boost at full bass when bus_select is set",
    )
    roughness_base: float = Field(
        default=1.0,
        ge=0.0,
        le=2.0,
        multiple_of=0.1,
        description="Roughness offset matching PixPal u_Float (roughness = base - attr.g)",
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
        description="Extra degrees per second at full bass when bus_select is set",
    )
    ambient: float = Field(
        default=0.25,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Ambient term",
    )
    _program: moderngl.Program | None = PrivateAttr(default=None)
    _vao: moderngl.VertexArray | None = PrivateAttr(default=None)
    _textures: dict[str, moderngl.Texture] = PrivateAttr(default_factory=dict)
    _mesh_interleaved: np.ndarray = PrivateAttr(
        default_factory=lambda: np.zeros(0, dtype=np.float32)
    )
    _indices: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype=np.uint32))
    _canvas_h: float = PrivateAttr(default=0.0)
    _gl_ready: bool = PrivateAttr(default=False)
    _prepared_path: str | None = PrivateAttr(default=None)
    _bass_history: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype="f4"))

    async def prepare(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        await asyncio.to_thread(self._prepare_sync, ctx)

    def _prepare_sync(self, ctx: PrepareContext) -> None:
        self._canvas_h = float(ctx.job.height)
        total = max(ctx.job.total_frames, 0)
        self._bass_history = precompute_bass_drive(self.bus_timeline(ctx), total)
        if self._prepared_path == self.source and self._mesh_interleaved.size > 0:
            return

        try:
            mesh_path = resolve_mesh_path(self.source, default_filename=_DEFAULT_MESH_FILE)
            positions, normals, uvs, indices = load_glb_mesh(mesh_path)
        except Exception as exc:
            record_prepare_asset_failure(
                ctx,
                kind="clip",
                ref_id=self.id,
                clip_type=self.clip_type,
                field="source",
                source=self.source,
                exc=exc,
            )
            log.warning("PixPalMesh %s: failed to load mesh — %s", self.id, exc)
            return
        n_tris = len(indices) // 3
        if n_tris > _MAX_TRIANGLES:
            raise ValueError(
                f"PixPal mesh too large: {n_tris:,} triangles (limit {_MAX_TRIANGLES:,}). "
                "Use a low-poly PixPal mesh."
            )
        positions, normals = normalize_mesh(positions, normals)
        self._mesh_interleaved = interleave_pos_norm_uv(positions, normals, uvs)
        self._indices = indices.astype(np.uint32)
        self._prepared_path = self.source
        self._release_gl()

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

        emissive = float(self.emissive_factor)
        if bus_active:
            emissive *= 1.0 + self.emissive_sensitivity * bass

        bind_pixpal_textures(prog, self._textures)
        write_pixpal_uniforms(
            prog,
            mvp=mvp,
            model_view=model_view,
            anim=float(ctx.time.t),
            roughness_base=float(self.roughness_base),
            emissive_factor=emissive,
            ambient=float(self.ambient),
            opacity=float(self.opacity),
            light_dir=light_dir,
        )

        prev_viewport = apply_clip_scissor(gl, b, self._canvas_h)
        draw_mesh_3d(gl, self._vao)
        restore_clip_scissor(gl, prev_viewport)

    def _release_gl(self) -> None:
        if self._vao is not None:
            self._vao.release()
        for tex in self._textures.values():
            tex.release()
        if self._program is not None:
            self._program.release()
        self._vao = None
        self._textures = {}
        self._program = None
        self._gl_ready = False

    def _upload_gl(self, gl: moderngl.Context) -> None:
        self._release_gl()
        self._program = gl.program(vertex_shader=PIXPAL_VERT, fragment_shader=PIXPAL_FRAG)
        self._textures = load_pixpal_textures(gl)
        self._vao = upload_pixpal_mesh(gl, self._program, self._mesh_interleaved, self._indices)
        self._gl_ready = True

    def _bass_for_frame(self, ctx: RenderContext) -> float:
        if not self.bus_active_for_draw(ctx):
            return 0.0
        if self._bass_history.shape[0] > 0:
            f = max(0, min(ctx.time.frame, self._bass_history.shape[0] - 1))
            return float(self._bass_history[f])
        return float(np.clip(ctx.audio_bus_frame.bass, 0.0, 1.0))
