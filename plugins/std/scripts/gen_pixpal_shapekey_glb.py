"""Build cube_imphenzia_shapekey.glb from cube_imphenzia.glb + squash morph."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from pygltflib import (
    GLTF2,
    Accessor,
    Attributes,
    Buffer,
    BufferView,
    Mesh,
    Node,
    Primitive,
    Scene,
)

from pixfabrica_std.mesh.gltf_loader import (
    bundled_glb_path,
    compute_vertex_normals,
    load_glb_mesh,
)

OUT = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "pixfabrica_std"
    / "mesh"
    / "resources"
    / "cube_imphenzia_shapekey.glb"
)


def _pad4(data: bytes) -> bytes:
    return data + b"\x00" * ((4 - len(data) % 4) % 4)


def main() -> None:
    src = bundled_glb_path("cube_imphenzia.glb")
    positions, normals, uvs, indices = load_glb_mesh(src)
    y_mid = float(np.median(positions[:, 1]))
    deltas = np.zeros_like(positions)
    top = positions[:, 1] > y_mid
    deltas[top, 1] = -0.2
    morphed = positions + deltas
    morph_normals = compute_vertex_normals(morphed, indices) - normals

    chunks = [
        positions.astype(np.float32).tobytes(),
        normals.astype(np.float32).tobytes(),
        uvs[:, :2].astype(np.float32).tobytes(),
        deltas.astype(np.float32).tobytes(),
        morph_normals.astype(np.float32).tobytes(),
        indices.astype(np.uint32).tobytes(),
    ]
    offsets: list[int] = []
    cursor = 0
    for chunk in chunks:
        offsets.append(cursor)
        cursor += len(chunk)
    blob = _pad4(b"".join(chunks))
    count = len(positions)

    views: list[BufferView] = []
    accessors: list[Accessor] = []

    def add_view(offset: int, length: int, target: int | None = None) -> int:
        views.append(BufferView(buffer=0, byteOffset=offset, byteLength=length, target=target))
        return len(views) - 1

    def add_accessor(view_idx: int, n: int, type_str: str, *, comp_type: int = 5126) -> int:
        accessors.append(
            Accessor(
                bufferView=view_idx,
                byteOffset=0,
                componentType=comp_type,
                count=n,
                type=type_str,
            )
        )
        return len(accessors) - 1

    pos_acc = add_accessor(add_view(offsets[0], len(chunks[0])), count, "VEC3")
    norm_acc = add_accessor(add_view(offsets[1], len(chunks[1])), count, "VEC3")
    uv_acc = add_accessor(add_view(offsets[2], len(chunks[2])), count, "VEC2")
    delta_acc = add_accessor(add_view(offsets[3], len(chunks[3])), count, "VEC3")
    morph_norm_acc = add_accessor(add_view(offsets[4], len(chunks[4])), count, "VEC3")
    idx_acc = add_accessor(
        add_view(offsets[5], len(chunks[5]), target=34963),
        len(indices),
        "SCALAR",
        comp_type=5125,
    )

    prim = Primitive(
        attributes=Attributes(POSITION=pos_acc, NORMAL=norm_acc, TEXCOORD_0=uv_acc),
        indices=idx_acc,
        targets=[Attributes(POSITION=delta_acc, NORMAL=morph_norm_acc)],
    )
    gltf = GLTF2(
        scene=0,
        scenes=[Scene(nodes=[0])],
        nodes=[Node(mesh=0)],
        meshes=[Mesh(primitives=[prim], extras={"targetNames": ["squash"]})],
        buffers=[Buffer(byteLength=len(blob))],
        bufferViews=views,
        accessors=accessors,
    )
    gltf.set_binary_blob(blob)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    gltf.save_binary(OUT)
    print(f"Wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
