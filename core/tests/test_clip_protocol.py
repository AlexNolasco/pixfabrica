from typing import ClassVar

from pixfabrica_core.clips import Clip, ClipTypeProtocol

# ── Example plugin clip (what a plugin author would write) ────────────────────


class RainClip(Clip):
    clip_type: ClassVar[str] = "acme-rain"
    intensity: float = 0.5
    color: str = "#ffffff"


# ── ClipTypeProtocol ──────────────────────────────────────────────────────────


def test_clip_instance_subclass_satisfies_protocol():
    assert isinstance(RainClip, ClipTypeProtocol)


def test_protocol_requires_clip_type():
    from pydantic import BaseModel

    class MissingClipType(BaseModel):
        intensity: float = 0.5

    assert not isinstance(MissingClipType, ClipTypeProtocol)


def test_model_dump_via_protocol():
    clip = RainClip(id="x", start=0.0, duration=3.0, intensity=0.8)
    data = clip.model_dump()
    assert data["intensity"] == 0.8
    assert data["color"] == "#ffffff"
    assert "node_type" not in data


def test_json_schema_via_protocol():
    schema = RainClip.model_json_schema()
    assert "intensity" in schema["properties"]
    assert "color" in schema["properties"]


# ── Clip ──────────────────────────────────────────────────────────────


def test_clip_instance_base_fields():
    clip = RainClip(id="abc", start=2.0, duration=5.0, intensity=0.3)
    assert clip.id == "abc"
    assert clip.start == 2.0
    assert clip.duration == 5.0
    assert clip.enabled is True
    assert clip.clip_type == "acme-rain"


def test_clip_instance_duration_optional():
    clip = RainClip(id="abc", start=0.0)
    assert clip.duration is None  # resolved later by RenderJob._resolve_timeline


def test_clip_instance_disabled():
    clip = RainClip(id="x", start=0.0, duration=3.0, enabled=False)
    assert clip.enabled is False
