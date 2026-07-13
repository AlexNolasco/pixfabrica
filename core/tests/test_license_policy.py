"""Tests for license metadata resolution and graph policy."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from pixfabrica_core.catalog import build_catalog_cache
from pixfabrica_core.clips import ClipCategory, ClipSkia
from pixfabrica_core.license_policy import (
    LICENSE_UNAVAILABLE_CODE,
    graph_license_violation,
    resolve_clip_license,
    resolve_plugin_license,
)
from pixfabrica_core.plugins import PluginManifest
from pixfabrica_core.plugins.discovery import DiscoveredPlugin


class _LicensedSample(ClipSkia):
    clip_type: ClassVar[str] = "test-licensed-sample"
    clip_category: ClassVar[ClipCategory] = ClipCategory.BACKGROUND
    clip_license: ClassVar[str] = "CC-BY-NC-SA-3.0"


class _DefaultSample(ClipSkia):
    clip_type: ClassVar[str] = "test-default-sample"
    clip_category: ClassVar[ClipCategory] = ClipCategory.BACKGROUND


class _PluginWithLicense:
    manifest = PluginManifest(
        name="test-plugin",
        display_name="Test",
        description="d",
        requires_core=">=0.1.0,<1.0",
        license="MIT",
    )
    clip_types = [_LicensedSample, _DefaultSample]
    effects: list[type] = []


def test_resolve_clip_license_override_and_default():
    assert resolve_clip_license(_LicensedSample, "MIT") == "CC-BY-NC-SA-3.0"
    assert resolve_clip_license(_DefaultSample, "MIT") == "MIT"
    assert resolve_plugin_license(_PluginWithLicense.manifest) == "MIT"


def test_build_catalog_cache_indexes_license():
    plugin = DiscoveredPlugin(
        package_name="test-pkg",
        version="1",
        author=None,
        plugin_class=_PluginWithLicense,
        plugin_package_dir=Path("."),
    )
    cache = build_catalog_cache([plugin])
    by_type = {clip.clip_type: clip.license for clip in cache.clips}
    assert by_type["test-licensed-sample"] == "CC-BY-NC-SA-3.0"
    assert by_type["test-default-sample"] == "MIT"


def test_graph_license_violation_blocks_excluded_clip():
    plugin = DiscoveredPlugin(
        package_name="test-pkg",
        version="1",
        author=None,
        plugin_class=_PluginWithLicense,
        plugin_package_dir=Path("."),
    )
    cache = build_catalog_cache([plugin])
    graph = {
        "tracks": [
            {
                "enabled": True,
                "clips": [
                    {"enabled": True, "clip_type": "test-licensed-sample"},
                ],
            }
        ]
    }
    violation = graph_license_violation(
        graph,
        catalog=cache,
        excluded_licenses=frozenset({"CC-BY-NC-SA-3.0"}),
    )
    assert violation is not None
    assert violation["code"] == LICENSE_UNAVAILABLE_CODE
    assert "test-licensed-sample" in violation["detail"]


def test_graph_license_violation_allows_when_not_excluded():
    plugin = DiscoveredPlugin(
        package_name="test-pkg",
        version="1",
        author=None,
        plugin_class=_PluginWithLicense,
        plugin_package_dir=Path("."),
    )
    cache = build_catalog_cache([plugin])
    graph = {
        "tracks": [
            {
                "enabled": True,
                "clips": [
                    {"enabled": True, "clip_type": "test-default-sample"},
                ],
            }
        ]
    }
    violation = graph_license_violation(
        graph,
        catalog=cache,
        excluded_licenses=frozenset({"CC-BY-NC-SA-3.0"}),
    )
    assert violation is None
