from __future__ import annotations

import json
from pathlib import Path

from pixfabrica_api.compose_graph import validate_graph_for_compose
from pixfabrica_api.compose_layout_lints import compose_layout_lints
from pixfabrica_core.clips import RenderJob

_REPO = Path(__file__).resolve().parents[2]
_HELLO = json.loads((_REPO / "cli" / "examples" / "hello_world.json").read_text(encoding="utf-8"))
_TRANSITIONS = json.loads(
    (_REPO / "cli" / "examples" / "hello_world_transitions.json").read_text(encoding="utf-8")
)


def _text_clip(text: str, *, offset_y: float = 0.5) -> dict:
    return {
        "clip_type": "std-static-text",
        "id": f"text-{text.lower()}",
        "start": 0.0,
        "text": text,
        "color": "neutral",
        "typography_role": "title_large",
        "offset_x": 0.5,
        "offset_y": offset_y,
        "align": "center",
    }


def _skia_track(track_id: str, *, start: float = 0.0, clips: list[dict]) -> dict:
    return {
        "clip_type": "std-skia-track",
        "id": track_id,
        "start": start,
        "clips": clips,
    }


def test_hello_world_has_no_layout_warnings() -> None:
    job = RenderJob.model_validate(_HELLO)
    warnings, hints = compose_layout_lints(job)
    assert warnings == []
    assert hints == []


def test_transitions_example_allows_intentional_overlap() -> None:
    job = RenderJob.model_validate(_TRANSITIONS)
    warnings, _ = compose_layout_lints(job)
    assert not any("start at 0" in w for w in warnings)


def test_overlapping_centered_text_warns() -> None:
    graph = {
        **_HELLO,
        "tracks": [
            _skia_track(
                "track-1",
                clips=[
                    {
                        "clip_type": "std-solid-background",
                        "id": "bg-1",
                        "start": 0.0,
                        "color": "background",
                    },
                    _text_clip("Title"),
                    _text_clip("Subtitle"),
                ],
            )
        ],
    }
    result = validate_graph_for_compose(graph)
    assert result["ok"] is True
    assert result.get("warnings")
    assert any("overlap" in w.lower() for w in result["warnings"])
    assert result.get("hints")


def test_multiple_hero_typography_roles_warns() -> None:
    graph = {
        **_HELLO,
        "tracks": [
            _skia_track(
                "track-1",
                clips=[
                    {
                        "clip_type": "std-solid-background",
                        "id": "bg-1",
                        "start": 0.0,
                        "color": "background",
                    },
                    _text_clip("Title", offset_y=0.35),
                    {
                        **_text_clip("Subtitle", offset_y=0.65),
                        "typography_role": "display_medium",
                    },
                ],
            )
        ],
    }
    graph["tracks"][0]["clips"][1]["typography_role"] = "display_large"
    result = validate_graph_for_compose(graph)
    assert result["ok"] is True
    assert any("hero typography" in w for w in result.get("warnings", []))


def test_multiple_tracks_at_zero_warns() -> None:
    bg = {
        "clip_type": "std-solid-background",
        "id": "bg",
        "start": 0.0,
        "color": "background",
    }
    graph = {
        **_HELLO,
        "tracks": [
            _skia_track("track-a", clips=[bg, _text_clip("A")]),
            _skia_track("track-b", clips=[bg, _text_clip("B")]),
        ],
    }
    result = validate_graph_for_compose(graph)
    assert result["ok"] is True
    assert any("start at 0" in w for w in result.get("warnings", []))
