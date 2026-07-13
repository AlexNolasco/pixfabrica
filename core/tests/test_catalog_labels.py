from pathlib import Path

from pixfabrica_core.catalog import build_catalog_cache, get_catalog_detail
from pixfabrica_core.catalog_labels import build_clip_labels
from pixfabrica_core.plugins.discovery import discover_plugins


def test_build_clip_labels_gradient_en():
    repo_plugins = Path(__file__).parent.parent.parent / "plugins"
    discovered, _ = discover_plugins(repo_plugins)
    cache = build_catalog_cache(discovered)
    detail = get_catalog_detail(cache, "std-gradient", lang="en")
    assert detail is not None
    assert detail.plugin_id == "pixfabrica-std"
    assert detail.labels is not None
    assert detail.labels["fields"]["opacity"]["label"] == "Opacity"
    assert "parameters" in detail.labels["sections"]


def test_build_clip_labels_f3_missing_key():
    ui = {
        "sections": [{"id": "parameters", "title_key": "ui.missing.section", "fields": ["foo"]}],
        "controls": {"foo": {"kind": "text"}},
    }
    labels = build_clip_labels(ui, "test-effect", {"en": {}}, "en", catalog_kind="effect")
    assert labels["fields"]["foo"]["label"] == "effect.test-effect.field.foo.label"
    assert labels["sections"]["parameters"] == "ui.missing.section"
