from typing import ClassVar

from pixfabrica_core.catalog import (
    build_clip_catalog,
    catalog_entry_for_clip_class,
)
from pixfabrica_core.clips import Clip, ClipCategory
from pixfabrica_core.composition.icon_registry import (
    ClipIconContext,
    StaticIconGenerator,
    register_icon,
    resolve_icon,
)


class _SampleClip(Clip):
    clip_type: ClassVar[str] = "test-sample-clip"
    clip_category: ClassVar[ClipCategory] = ClipCategory.MESH


CUSTOM_SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"></svg>'


def test_resolve_icon_category_default():
    ctx = ClipIconContext(
        clip_type="unregistered-clip",
        category=str(ClipCategory.MESH),
        tags=[],
    )
    icon = resolve_icon(ctx)
    assert icon.startswith("<svg")
    assert "polyline" in icon  # mesh category icon


def test_register_icon_override():
    register_icon("test-custom", StaticIconGenerator(CUSTOM_SVG))
    ctx = ClipIconContext(clip_type="test-custom", category=str(ClipCategory.UTILITY), tags=[])
    assert resolve_icon(ctx) == CUSTOM_SVG


def test_catalog_entry_for_clip_class():
    entry = catalog_entry_for_clip_class(_SampleClip)
    assert entry is not None
    assert entry.clip_type == "test-sample-clip"
    assert entry.category == str(ClipCategory.MESH)
    assert entry.icon.startswith("<svg")
    assert "properties" in entry.parameters


def test_build_clip_catalog_empty():
    assert build_clip_catalog([]) == []
