import json
from pathlib import Path

from pixfabrica_api.plugin_registry import ensure_plugins_registered
from pixfabrica_core.clips import RenderJob
from pixfabrica_core.composition.unknown import UnknownClip
from pixfabrica_std.text.static_text import StaticText

_REPO = Path(__file__).resolve().parents[2]
_HELLO = _REPO / "cli" / "examples" / "hello_world.json"


def test_register_discovered_plugins_resolves_std_nodes() -> None:
    ensure_plugins_registered()
    data = json.loads(_HELLO.read_text(encoding="utf-8"))
    job = RenderJob.model_validate(data)
    assert job.tracks
    clips = job.tracks[0].clips
    assert clips
    assert isinstance(clips[1], StaticText)
    assert not isinstance(clips[0], UnknownClip)
