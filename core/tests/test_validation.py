"""Tests for stepped-float snapping during clip deserialization."""

from __future__ import annotations

from pixfabrica_core.composition.registry import deserialize_clip, register_clip_type
from pixfabrica_core.validation import snap_float, snap_payload_fields
from pixfabrica_std.background.hex_background_gl import HexBackgroundGL
from pixfabrica_std.mesh.gltf_mesh_gl import GltfMeshGL


def test_snap_float_handles_binary_float_steps() -> None:
    assert snap_float(0.25, 0.1) == 0.2
    assert snap_float(0.327, 0.01) == 0.33


def test_hex_background_roundtrips_after_model_dump() -> None:
    register_clip_type(HexBackgroundGL)
    clip = HexBackgroundGL(id="hex-1", start=0.0, duration=10.0)
    payload = {**clip.model_dump(mode="json"), "clip_type": HexBackgroundGL.clip_type}
    restored = deserialize_clip(payload)
    assert isinstance(restored, HexBackgroundGL)
    assert restored.zoom == 0.33
    assert restored.bevel_size == 0.2
    assert restored.fog_strength == 0.2


def test_gltf_mesh_ambient_roundtrips_after_model_dump() -> None:
    register_clip_type(GltfMeshGL)
    clip = GltfMeshGL(id="mesh-1", start=0.0, duration=10.0, mesh="skull")
    payload = {**clip.model_dump(mode="json"), "clip_type": GltfMeshGL.clip_type}
    restored = deserialize_clip(payload)
    assert isinstance(restored, GltfMeshGL)
    assert restored.ambient == 0.2


def test_snap_payload_fields_only_touches_declared_fields() -> None:
    payload = snap_payload_fields(
        HexBackgroundGL,
        {"zoom": 0.327, "bevel_size": 0.1875, "extra": 1.23},
    )
    assert payload["zoom"] == 0.33
    assert payload["bevel_size"] == 0.2
    assert payload["extra"] == 1.23


def test_snap_payload_fields_clamps_to_bounds() -> None:
    from pixfabrica_std.text.dynamic_text import DynamicText

    # Stored documents may hold values from an older, wider schema range
    # (e.g. spread was 0-8 before narrowing to 0-4) — clamp, don't reject.
    payload = snap_payload_fields(DynamicText, {"spread": 6.1, "opacity": -0.5})
    assert payload["spread"] == 4.0
    assert payload["opacity"] == 0.0


def test_stale_out_of_range_value_still_deserializes() -> None:
    from pixfabrica_std.text.dynamic_text import DynamicText

    register_clip_type(DynamicText)
    clip = deserialize_clip({"clip_type": DynamicText.clip_type, "id": "dt-1", "spread": 6.1})
    assert isinstance(clip, DynamicText)
    assert clip.spread == 4.0
