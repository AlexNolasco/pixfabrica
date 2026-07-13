from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any, Literal

import numpy as np
from pygltflib import GLTF2

DEFAULT_PIXPAL_SHAPEKEY_MESH_FILE = "cube_imphenzia_shapekey.glb"

MeshAsset = Literal["skull", "suzanne", "cube"]

MESH_ASSET_FILES: dict[MeshAsset, str] = {
    "skull": "skull.glb",
    "suzanne": "suzanne.glb",
    "cube": "cube.glb",
}

_COMPONENT_DTYPE: dict[int, Any] = {
    5120: np.int8,
    5121: np.uint8,
    5122: np.int16,
    5123: np.uint16,
    5125: np.uint32,
    5126: np.float32,
}
_TYPE_COMPONENTS: dict[str, int] = {
    "SCALAR": 1,
    "VEC2": 2,
    "VEC3": 3,
    "VEC4": 4,
}


def bundled_glb_path(filename: str) -> Path:
    return Path(str(files("pixfabrica_std") / "mesh" / "resources" / filename))


def resolve_mesh_path(path: str, *, default_filename: str) -> Path:
    """Empty path loads a bundled mesh; otherwise require an absolute on-disk path."""
    if not path.strip():
        return bundled_glb_path(default_filename)
    resolved = Path(path)
    if not resolved.is_file():
        raise FileNotFoundError(f"Mesh file not found: {path}")
    return resolved


def load_glb_triangles(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    gltf = GLTF2().load(path)
    if gltf is None:
        raise ValueError(f"Failed to load glTF: {path}")
    if not gltf.meshes:
        raise _empty_glb_error(path)
    prim = gltf.meshes[0].primitives[0]
    pos_idx = prim.attributes.POSITION
    if pos_idx is None:
        raise ValueError(f"No POSITION accessor in {path}")
    positions = _read_accessor(gltf, pos_idx)

    if prim.attributes.NORMAL is not None:
        normals = _read_accessor(gltf, prim.attributes.NORMAL)
    else:
        normals = np.zeros_like(positions, dtype=np.float32)

    if prim.indices is None:
        raise ValueError(f"Mesh in {path} must be indexed")
    indices = _read_accessor(gltf, prim.indices).reshape(-1).astype(np.uint32)

    if normals.shape == positions.shape and not np.any(normals):
        normals = compute_vertex_normals(positions, indices)

    return positions, normals, indices


def load_glb_mesh(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Load first mesh primitive with POSITION, NORMAL, TEXCOORD_0, and indices."""
    gltf = GLTF2().load(path)
    if gltf is None:
        raise ValueError(f"Failed to load glTF: {path}")
    if not gltf.meshes:
        raise _empty_glb_error(path)
    prim = gltf.meshes[0].primitives[0]
    pos_idx = prim.attributes.POSITION
    if pos_idx is None:
        raise ValueError(f"No POSITION accessor in {path}")
    positions = _read_accessor(gltf, pos_idx)

    if prim.attributes.NORMAL is not None:
        normals = _read_accessor(gltf, prim.attributes.NORMAL)
    else:
        normals = np.zeros_like(positions, dtype=np.float32)

    tex_idx = prim.attributes.TEXCOORD_0
    if tex_idx is None:
        raise ValueError(f"TEXCOORD_0 required for PixPal mesh in {path}")
    uvs = _read_accessor(gltf, tex_idx)
    if uvs.shape[1] < 2:
        raise ValueError(f"Invalid TEXCOORD_0 in {path}")

    if prim.indices is None:
        raise ValueError(f"Mesh in {path} must be indexed")
    indices = _read_accessor(gltf, prim.indices).reshape(-1).astype(np.uint32)

    if normals.shape == positions.shape and not np.any(normals):
        normals = compute_vertex_normals(positions, indices)

    return positions, normals, uvs[:, :2], indices


@dataclass(frozen=True, slots=True)
class LoadedMorphMesh:
    positions: np.ndarray
    normals: np.ndarray
    indices: np.ndarray
    morph_names: tuple[str, ...]
    morph_position_deltas: dict[str, np.ndarray]
    morph_normal_deltas: dict[str, np.ndarray]
    uvs: np.ndarray | None = None


def load_glb_pixpal_morph_mesh(path: Path) -> LoadedMorphMesh:
    """Load morph mesh with POSITION, NORMAL, TEXCOORD_0, indices, and morph targets."""
    gltf = GLTF2().load(path)
    if gltf is None:
        raise ValueError(f"Failed to load glTF: {path}")
    if not gltf.meshes:
        raise _empty_glb_error(path)
    mesh = gltf.meshes[0]
    prim = mesh.primitives[0]
    pos_idx = prim.attributes.POSITION
    if pos_idx is None:
        raise ValueError(f"No POSITION accessor in {path}")
    positions = _read_accessor(gltf, pos_idx)

    if prim.attributes.NORMAL is not None:
        normals = _read_accessor(gltf, prim.attributes.NORMAL)
    else:
        normals = np.zeros_like(positions, dtype=np.float32)

    tex_idx = prim.attributes.TEXCOORD_0
    if tex_idx is None:
        raise ValueError(f"TEXCOORD_0 required for PixPal morph mesh in {path}")
    uvs = _read_accessor(gltf, tex_idx)
    if uvs.shape[1] < 2:
        raise ValueError(f"Invalid TEXCOORD_0 in {path}")

    if prim.indices is None:
        raise ValueError(f"Mesh in {path} must be indexed")
    indices = _read_accessor(gltf, prim.indices).reshape(-1).astype(np.uint32)

    if normals.shape == positions.shape and not np.any(normals):
        normals = compute_vertex_normals(positions, indices)

    targets = prim.targets or []
    if not targets:
        raise ValueError(f"No morph targets in {path}")

    names = _morph_target_names(mesh, len(targets))
    morph_position_deltas: dict[str, np.ndarray] = {}
    morph_normal_deltas: dict[str, np.ndarray] = {}
    for i, target in enumerate(targets):
        name = names[i]
        pos_attr = _target_accessor(target, "POSITION")
        if pos_attr is None:
            raise ValueError(f"Morph target {name!r} in {path} has no POSITION delta")
        delta_pos = _read_accessor(gltf, pos_attr)
        if delta_pos.shape != positions.shape:
            raise ValueError(f"Morph POSITION delta shape mismatch for {name!r} in {path}")
        morph_position_deltas[name] = delta_pos
        norm_attr = _target_accessor(target, "NORMAL")
        if norm_attr is not None:
            delta_norm = _read_accessor(gltf, norm_attr)
            if delta_norm.shape != positions.shape:
                raise ValueError(f"Morph NORMAL delta shape mismatch for {name!r} in {path}")
            morph_normal_deltas[name] = delta_norm
        else:
            morph_normal_deltas[name] = np.zeros_like(positions, dtype=np.float32)

    return LoadedMorphMesh(
        positions=positions,
        normals=normals,
        indices=indices,
        morph_names=tuple(names),
        morph_position_deltas=morph_position_deltas,
        morph_normal_deltas=morph_normal_deltas,
        uvs=uvs[:, :2],
    )


def normalize_mesh(positions: np.ndarray, normals: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    positions_n, _, _, _ = normalize_mesh_with_morphs(positions, normals, {}, {})
    return positions_n, normals


def normalize_mesh_with_morphs(
    positions: np.ndarray,
    normals: np.ndarray,
    morph_position_deltas: dict[str, np.ndarray],
    morph_normal_deltas: dict[str, np.ndarray],
) -> tuple[np.ndarray, np.ndarray, dict[str, np.ndarray], dict[str, np.ndarray]]:
    lo = positions.min(axis=0)
    hi = positions.max(axis=0)
    center = (lo + hi) * 0.5
    extent = float(np.max(hi - lo))
    if extent < 1e-8:
        extent = 1.0
    inv_extent = 1.0 / extent
    pos_n = (positions - center) * inv_extent
    morph_pos_n = {k: v * inv_extent for k, v in morph_position_deltas.items()}
    morph_norm_n = dict(morph_normal_deltas)
    return pos_n, normals, morph_pos_n, morph_norm_n


def interleave_pos_norm(positions: np.ndarray, normals: np.ndarray) -> np.ndarray:
    return np.hstack([positions, normals]).astype(np.float32, copy=False)


def interleave_pos_norm_uv_morph(
    positions: np.ndarray,
    normals: np.ndarray,
    uvs: np.ndarray,
    morph_positions: np.ndarray,
    morph_normals: np.ndarray,
) -> np.ndarray:
    return np.hstack([positions, normals, uvs[:, :2], morph_positions, morph_normals]).astype(
        np.float32, copy=False
    )


def interleave_pos_norm_uv(
    positions: np.ndarray, normals: np.ndarray, uvs: np.ndarray
) -> np.ndarray:
    return np.hstack([positions, normals, uvs[:, :2]]).astype(np.float32, copy=False)


def compute_vertex_normals(positions: np.ndarray, indices: np.ndarray) -> np.ndarray:
    normals = np.zeros_like(positions, dtype=np.float32)
    tris = indices.reshape(-1, 3)
    for i0, i1, i2 in tris:
        p0, p1, p2 = positions[i0], positions[i1], positions[i2]
        n = np.cross(p1 - p0, p2 - p0)
        normals[i0] += n
        normals[i1] += n
        normals[i2] += n
    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    lengths = np.maximum(lengths, 1e-8)
    return normals / lengths


def _target_accessor(target: Any, key: str) -> int | None:
    value = target.get(key) if isinstance(target, dict) else getattr(target, key, None)
    return int(value) if value is not None else None


def _morph_target_names(mesh: Any, target_count: int) -> list[str]:
    extras = mesh.extras or {}
    raw_names = extras.get("targetNames") if isinstance(extras, dict) else None
    if isinstance(raw_names, list) and len(raw_names) >= target_count:
        return [str(raw_names[i]) for i in range(target_count)]
    return [f"target_{i}" for i in range(target_count)]


def _empty_glb_error(path: Path) -> ValueError:
    return ValueError(
        f"No meshes in {path} — the file exists but has no geometry "
        "(empty Blender export or JSON-only stub). Re-export the .glb with mesh data."
    )


def _read_accessor(gltf: GLTF2, accessor_index: int) -> np.ndarray:
    accessor = gltf.accessors[accessor_index]
    comp_type = accessor.componentType
    acc_type = accessor.type
    if comp_type is None or acc_type is None:
        raise ValueError(f"Accessor {accessor_index} missing componentType or type")
    dtype = _COMPONENT_DTYPE[comp_type]
    ncomp = _TYPE_COMPONENTS[acc_type]
    count = accessor.count

    if accessor.bufferView is not None:
        arr = _read_accessor_dense(gltf, accessor, dtype=dtype, ncomp=ncomp)
    elif accessor.sparse is not None:
        arr = np.zeros((count, ncomp), dtype=np.float32)
    else:
        raise ValueError(
            f"Accessor {accessor_index} has no bufferView "
            "(re-export as .glb with mesh data embedded, not a JSON-only .gltf stub)"
        )

    if accessor.sparse is not None:
        _apply_sparse_accessor(gltf, accessor, arr, dtype=dtype, ncomp=ncomp)

    if accessor.normalized:
        max_val = float(np.iinfo(dtype).max) if np.issubdtype(dtype, np.integer) else 1.0
        arr = arr.astype(np.float32) / max_val
    return arr.astype(np.float32, copy=False)


def _read_accessor_dense(
    gltf: GLTF2,
    accessor: Any,
    *,
    dtype: Any,
    ncomp: int,
) -> np.ndarray:
    if accessor.bufferView is None:
        raise ValueError("Accessor has no bufferView")
    view = gltf.bufferViews[accessor.bufferView]
    blob = gltf.binary_blob()
    if blob is None:
        raise ValueError("glTF has no binary blob (expected .glb)")
    offset = (view.byteOffset or 0) + (accessor.byteOffset or 0)
    count = accessor.count
    raw = np.frombuffer(blob, dtype=dtype, count=count * ncomp, offset=offset)
    return raw.reshape(count, ncomp).astype(np.float32, copy=True)


def _sparse_field(part: Any, key: str) -> Any:
    if isinstance(part, dict):
        return part.get(key)
    return getattr(part, key, None)


def _apply_sparse_accessor(
    gltf: GLTF2,
    accessor: Any,
    arr: np.ndarray,
    *,
    dtype: Any,
    ncomp: int,
) -> None:
    sparse = accessor.sparse
    if sparse is None:
        return
    indices_part = _sparse_field(sparse, "indices")
    values_part = _sparse_field(sparse, "values")
    if indices_part is None or values_part is None:
        raise ValueError("Sparse accessor is missing indices or values")

    idx_view_i = _sparse_field(indices_part, "bufferView")
    val_view_i = _sparse_field(values_part, "bufferView")
    if idx_view_i is None or val_view_i is None:
        raise ValueError("Sparse accessor indices/values have no bufferView")

    blob = gltf.binary_blob()
    if blob is None:
        raise ValueError("glTF has no binary blob (expected .glb)")

    idx_comp = _sparse_field(indices_part, "componentType")
    if idx_comp is None:
        raise ValueError("Sparse accessor indices missing componentType")
    idx_dtype = _COMPONENT_DTYPE[idx_comp]
    sparse_count = int(_sparse_field(sparse, "count") or 0)

    idx_view = gltf.bufferViews[int(idx_view_i)]
    idx_offset = (idx_view.byteOffset or 0) + int(_sparse_field(indices_part, "byteOffset") or 0)
    indices = np.frombuffer(blob, dtype=idx_dtype, count=sparse_count, offset=idx_offset).astype(
        np.int64, copy=False
    )

    val_view = gltf.bufferViews[int(val_view_i)]
    val_offset = (val_view.byteOffset or 0) + int(_sparse_field(values_part, "byteOffset") or 0)
    values = np.frombuffer(
        blob, dtype=dtype, count=sparse_count * ncomp, offset=val_offset
    ).reshape(sparse_count, ncomp)

    for i, vtx in enumerate(indices):
        arr[int(vtx)] = values[i]
