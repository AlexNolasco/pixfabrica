"""Tests for plugin clip_types discovery helper."""

from __future__ import annotations

from typing import ClassVar

from pixfabrica_core.plugins import PluginManifest, plugin_clip_types


class _EmptyPlugin:
    manifest = PluginManifest(
        name="empty",
        display_name="Empty",
        description="",
        requires_core=">=0.1.0,<1.0",
    )


class _ClipTypesPlugin:
    manifest = PluginManifest(
        name="modern",
        display_name="Modern",
        description="",
        requires_core=">=0.1.0,<1.0",
    )
    clip_types: ClassVar[list[type]] = [str]


def test_plugin_clip_types_reads_clip_types_attr():
    assert plugin_clip_types(_ClipTypesPlugin) == [str]


def test_plugin_clip_types_empty_when_missing():
    assert plugin_clip_types(_EmptyPlugin) == []
