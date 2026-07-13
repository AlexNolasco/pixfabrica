from __future__ import annotations

from pixfabrica_api.catalog_cache import rebuild_catalog_cache
from pixfabrica_api.compose_catalog import (
    get_clip_detail_for_compose,
    list_catalog_clips_for_compose,
)
from pixfabrica_api.compose_graph import validate_graph_for_compose
from pixfabrica_api.compose_graph_builder import build_graph_from_spec
from pixfabrica_api.plugin_registry import ensure_plugins_registered


def test_list_catalog_clips_includes_static_text() -> None:
    rebuild_catalog_cache()
    result = list_catalog_clips_for_compose(track_kind="skia", category="text")
    assert result["ok"] is True
    types = {n["clip_type"] for n in result["clips"]}
    assert "std-static-text" in types


def test_get_clip_detail_static_text() -> None:
    rebuild_catalog_cache()
    detail = get_clip_detail_for_compose("std-static-text")
    assert detail["ok"] is True
    assert detail["track_kind"] == "skia"
    assert "text" in detail["defaults"] or "text" in detail["parameters"]


def test_build_graph_hello_world_style() -> None:
    rebuild_catalog_cache()
    ensure_plugins_registered()
    graph = build_graph_from_spec(
        {
            "title": "Hello, World!",
            "description": "Built via compose spec",
            "duration": 5.0,
            "tracks": [
                {
                    "track_kind": "skia",
                    "clips": [
                        {"clip_type": "std-solid-background", "params": {"color": "background"}},
                        {
                            "clip_type": "std-static-text",
                            "params": {
                                "text": "Hello, World!",
                                "color": "neutral",
                                "typography_role": "title_large",
                                "offset_x": 0.5,
                                "offset_y": 0.5,
                                "align": "center",
                            },
                        },
                    ],
                }
            ],
        }
    )
    validation = validate_graph_for_compose(graph)
    assert validation["ok"] is True
    assert graph["title"] == "Hello, World!"
    assert len(graph["tracks"]) == 1
    assert len(graph["tracks"][0]["clips"]) == 2
