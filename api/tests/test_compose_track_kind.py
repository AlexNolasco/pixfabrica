from __future__ import annotations

import pytest

from pixfabrica_api.catalog_cache import rebuild_catalog_cache
from pixfabrica_api.compose_graph import validate_graph_for_compose
from pixfabrica_api.compose_graph_builder import build_graph_from_spec
from pixfabrica_api.plugin_registry import ensure_plugins_registered


@pytest.fixture(autouse=True)
def _catalog() -> None:
    rebuild_catalog_cache()
    ensure_plugins_registered()


def test_build_graph_rejects_skia_clip_on_gl_track() -> None:
    with pytest.raises(ValueError, match="std-static-text belongs on skia tracks only"):
        build_graph_from_spec(
            {
                "title": "Wrong track",
                "tracks": [
                    {
                        "track_kind": "gl",
                        "clips": [{"clip_type": "std-static-text", "params": {"text": "Nope"}}],
                    }
                ],
            }
        )


def test_build_graph_rejects_gl_clip_on_skia_track() -> None:
    with pytest.raises(ValueError, match="std-fractal-plasma-gl belongs on gl tracks only"):
        build_graph_from_spec(
            {
                "title": "Wrong track",
                "tracks": [
                    {
                        "track_kind": "skia",
                        "clips": [{"clip_type": "std-fractal-plasma-gl"}],
                    }
                ],
            }
        )


def test_validate_graph_rejects_mismatched_track_kind() -> None:
    graph = build_graph_from_spec(
        {
            "title": "Skia ok",
            "tracks": [
                {
                    "track_kind": "skia",
                    "clips": [
                        {"clip_type": "std-solid-background"},
                        {"clip_type": "std-static-text", "params": {"text": "Hi"}},
                    ],
                }
            ],
        }
    )
    graph["tracks"][0]["clip_type"] = "std-gl-track"
    result = validate_graph_for_compose(graph)
    assert result["ok"] is False
    assert any("requires skia tracks only" in err for err in result["errors"])
