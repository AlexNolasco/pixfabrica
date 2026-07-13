from pathlib import Path
from typing import ClassVar

from pixfabrica_core.catalog import (
    build_catalog_cache,
    get_effect_catalog_detail,
    humanize_clip_type,
    infer_track_kind,
    list_catalog_items,
    load_plugin_nls,
    resolve_clip_label,
)
from pixfabrica_core.clips import Clip, ClipCategory, ClipGL, ClipSkia, GLPostProcessClip
from pixfabrica_core.plugins.discovery import DiscoveredPlugin, discover_plugins


class _SkiaSample(ClipSkia):
    clip_type: ClassVar[str] = "test-skia-sample"
    clip_category: ClassVar[ClipCategory] = ClipCategory.BACKGROUND


class _GLSample(ClipGL):
    clip_type: ClassVar[str] = "test-gl-sample"
    clip_category: ClassVar[ClipCategory] = ClipCategory.EFFECTS


class _PostSample(GLPostProcessClip):
    clip_type: ClassVar[str] = "test-post-sample"
    clip_category: ClassVar[ClipCategory] = ClipCategory.POSTPROCESS


class _SoundOnly(Clip):
    clip_type: ClassVar[str] = "test-sound-only"
    clip_category: ClassVar[ClipCategory] = ClipCategory.AUDIO


def test_infer_track_kind():
    assert infer_track_kind(_SkiaSample) == "skia"
    assert infer_track_kind(_GLSample) == "gl"
    assert infer_track_kind(_PostSample) == "post"
    assert infer_track_kind(_SoundOnly) is None


def test_humanize_clip_type():
    assert humanize_clip_type("std-animated-gradient-gl") == "Animated Gradient Gl"


class _TestPlugin:
    clip_types = [_SkiaSample, _SoundOnly]


def test_build_catalog_cache_filters_non_visual():
    plugin = DiscoveredPlugin(
        package_name="test-pkg",
        version="1",
        author=None,
        plugin_class=_TestPlugin,
        plugin_package_dir=Path("."),
    )
    cache = build_catalog_cache([plugin])
    assert len(cache.clips) == 1
    assert cache.clips[0].clip_type == "test-skia-sample"


class _TestPluginTwo:
    clip_types = [_SkiaSample, _GLSample]


def test_list_catalog_items_lang_and_track_kind():
    plugin = DiscoveredPlugin(
        package_name="test-pkg",
        version="1",
        author=None,
        plugin_class=_TestPluginTwo,
        plugin_package_dir=Path("."),
    )
    cache = build_catalog_cache([plugin])
    skia_only = list_catalog_items(cache, lang="en", track_kind="skia")
    assert [n.clip_type for n in skia_only] == ["test-skia-sample"]


def test_std_plugin_nls_labels():
    repo_plugins = Path(__file__).parent.parent.parent / "plugins"
    discovered, _ = discover_plugins(repo_plugins)
    std = next(p for p in discovered if p.package_name == "pixfabrica-std")
    nls = load_plugin_nls(std.plugin_package_dir)
    label = resolve_clip_label(nls, "en", "std-gradient")
    assert label == "Linear Gradient"


def test_std_catalog_has_visual_nodes():
    repo_plugins = Path(__file__).parent.parent.parent / "plugins"
    discovered, _ = discover_plugins(repo_plugins)
    cache = build_catalog_cache(discovered)
    kinds = {n.track_kind for n in cache.clips}
    assert "skia" in kinds
    assert "gl" in kinds
    assert "post" in kinds


def test_std_catalog_detail_for_gradient():
    repo_plugins = Path(__file__).parent.parent.parent / "plugins"
    discovered, _ = discover_plugins(repo_plugins)
    cache = build_catalog_cache(discovered)
    detail = cache.details.get("std-gradient")
    assert detail is not None
    assert isinstance(detail.ui.get("controls"), dict)
    assert isinstance(detail.parameters_schema, dict)
    assert isinstance(detail.defaults, dict)


def test_std_effects_catalog_detail_for_invert_gl():
    repo_plugins = Path(__file__).parent.parent.parent / "plugins"
    discovered, _ = discover_plugins(repo_plugins)
    cache = build_catalog_cache(discovered)
    detail = get_effect_catalog_detail(cache, "std-invert-gl", lang="es")
    assert detail is not None
    assert detail.plugin_id == "pixfabrica-std-effects"
    assert isinstance(detail.ui.get("controls"), dict)
    assert "mix" in detail.ui["controls"]
