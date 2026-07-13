"""Tests for graph-level GL requirement detection."""

from __future__ import annotations

from pixfabrica_core.capabilities.gl import graph_requires_gl_context
from pixfabrica_core.catalog import build_catalog_cache
from pixfabrica_core.composition.effect_registry import register_effect
from pixfabrica_core.composition.registry import register_clip_type
from pixfabrica_core.plugins.discovery import discover_plugins


def _catalog():
    discovered, _failed = discover_plugins()
    for plugin in discovered:
        for clip_cls in plugin.clip_types:
            register_clip_type(clip_cls)
        for effect_cls in plugin.effects:
            register_effect(effect_cls)
    return build_catalog_cache(discovered)


def test_skia_graph_does_not_require_gl() -> None:
    catalog = _catalog()
    graph = {
        "tracks": [
            {
                "clip_type": "std-skia-track",
                "id": "track-1",
                "clips": [
                    {
                        "clip_type": "std-solid-background",
                        "id": "bg-1",
                    }
                ],
            }
        ]
    }
    assert graph_requires_gl_context(graph, catalog=catalog) is False


def test_gl_track_requires_gl() -> None:
    catalog = _catalog()
    graph = {
        "tracks": [
            {
                "clip_type": "std-gl-track",
                "id": "track-1",
                "clips": [],
            }
        ]
    }
    assert graph_requires_gl_context(graph, catalog=catalog) is True


def test_post_track_requires_gl() -> None:
    catalog = _catalog()
    graph = {
        "tracks": [
            {
                "clip_type": "std-post-track",
                "id": "track-1",
                "clips": [],
            }
        ]
    }
    assert graph_requires_gl_context(graph, catalog=catalog) is True


def test_web_track_type_field_requires_gl() -> None:
    catalog = _catalog()
    graph = {
        "tracks": [
            {
                "id": "track-1",
                "trackType": "gl",
                "clips": [],
            }
        ]
    }
    assert graph_requires_gl_context(graph, catalog=catalog) is True
