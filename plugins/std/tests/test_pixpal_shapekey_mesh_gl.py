"""Tests for std-pixpal-shapekey-mesh morph loading and prepare."""

from __future__ import annotations

import asyncio
from pathlib import Path

import numpy as np
import pytest

from pixfabrica_core.audio.bus import N_SPECTRUM, AudioBusFrame
from pixfabrica_core.clips import JobInfo, PrepareContext
from pixfabrica_core.theme.color import ColorPalette
from pixfabrica_core.theme.typography import FontPalette
from pixfabrica_std.mesh.gltf_loader import (
    DEFAULT_PIXPAL_SHAPEKEY_MESH_FILE,
    _read_accessor,
    bundled_glb_path,
    load_glb_pixpal_morph_mesh,
)
from pixfabrica_std.mesh.pixpal_shapekey_mesh_gl import PixPalShapeKeyMeshGL


def _prepare_ctx(tmp_path: Path, *, audio: dict | None = None) -> PrepareContext:
    ji = JobInfo(
        title="t",
        description="d",
        width=640,
        height=480,
        fps=30.0,
        duration=2.0,
        colors=ColorPalette(),
        typography=FontPalette(),
        locale="en",
    )
    td = tmp_path / "temp"
    cd = tmp_path / "cache"
    td.mkdir(exist_ok=True)
    cd.mkdir(exist_ok=True)
    return PrepareContext(job=ji, temp_dir=td, cache_dir=cd, audio=audio or {})


def test_read_accessor_supports_sparse_only_morph_delta() -> None:
    from pygltflib import (
        GLTF2,
        Accessor,
        AccessorSparseIndices,
        AccessorSparseValues,
        Buffer,
        BufferView,
        Sparse,
    )

    sparse_vals = np.array([[0.0, 0.2, 0.0], [0.0, -0.1, 0.0]], dtype=np.float32)
    sparse_idx = np.array([1, 3], dtype=np.uint32)
    blob = sparse_idx.tobytes() + sparse_vals.tobytes()
    gltf = GLTF2(
        accessors=[
            Accessor(
                bufferView=None,
                componentType=5126,
                count=4,
                type="VEC3",
                sparse=Sparse(
                    count=2,
                    indices=AccessorSparseIndices(bufferView=0, byteOffset=0, componentType=5125),
                    values=AccessorSparseValues(bufferView=1, byteOffset=0),
                ),
            )
        ],
        bufferViews=[
            BufferView(buffer=0, byteOffset=0, byteLength=8),
            BufferView(buffer=0, byteOffset=8, byteLength=24),
        ],
        buffers=[Buffer(byteLength=len(blob))],
    )
    gltf.set_binary_blob(blob)
    out = _read_accessor(gltf, 0)
    assert out.shape == (4, 3)
    assert out[1, 1] == pytest.approx(0.2)
    assert out[3, 1] == pytest.approx(-0.1)


def test_bundled_pixpal_shapekey_has_uvs_and_squash() -> None:
    path = bundled_glb_path(DEFAULT_PIXPAL_SHAPEKEY_MESH_FILE)
    if not path.is_file():
        pytest.skip("bundled cube_imphenzia_shapekey.glb missing")
    loaded = load_glb_pixpal_morph_mesh(path)
    assert loaded.uvs is not None
    assert loaded.uvs.shape[1] == 2
    assert "squash" in loaded.morph_names


def test_prepare_pixpal_shapekey_default_bundled(tmp_path: Path) -> None:
    path = bundled_glb_path(DEFAULT_PIXPAL_SHAPEKEY_MESH_FILE)
    if not path.is_file():
        pytest.skip("bundled cube_imphenzia_shapekey.glb missing")

    frames = [
        AudioBusFrame(
            spectrum=[0.0] * N_SPECTRUM,
            bass=0.2,
            mid=0.1,
            high=0.1,
            beat=False,
            amplitude=0.2 + 0.6 * (i / 29),
        )
        for i in range(30)
    ]
    clip = PixPalShapeKeyMeshGL(id="psk", morph_name="squash", bus_select="voice")
    ctx = _prepare_ctx(tmp_path, audio={"voice": frames})
    asyncio.run(clip.prepare(ctx))

    assert clip._mesh_interleaved.size > 0  # noqa: SLF001
    assert clip._weight_history.shape[0] == 60  # noqa: SLF001
    assert float(clip._weight_history[-1]) > 0.0  # noqa: SLF001


def test_prepare_fails_on_unknown_morph_name(tmp_path: Path) -> None:
    path = bundled_glb_path(DEFAULT_PIXPAL_SHAPEKEY_MESH_FILE)
    if not path.is_file():
        pytest.skip("bundled cube_imphenzia_shapekey.glb missing")

    clip = PixPalShapeKeyMeshGL(id="psk", morph_name="missing_morph")
    ctx = _prepare_ctx(tmp_path)
    with pytest.raises(ValueError, match="not found"):
        asyncio.run(clip.prepare(ctx))


def test_shapekey_weight_attack_alpha_faster_than_release() -> None:
    import math

    fps = 30.0
    attack_alpha = 1.0 - math.exp(-1.0 / max(fps * 0.05, 1.0))
    release_alpha = 1.0 - math.exp(-1.0 / max(fps * 0.45, 1.0))
    assert attack_alpha > release_alpha
