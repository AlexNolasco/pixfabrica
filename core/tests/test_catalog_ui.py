import json

from pixfabrica_core.catalog_ui import (
    deep_merge_dict,
    extract_defaults_from_clip_class,
    extract_defaults_from_json_schema,
    merged_ui_spec_for_clip,
    to_json_safe_catalog_value,
)
from pixfabrica_core.theme.color import Color


def test_deep_merge_dict_nested():
    base = {"controls": {"opacity": {"kind": "slider"}, "start": {"kind": "number"}}}
    override = {"controls": {"opacity": {"show_as": "percent"}}}
    merged = deep_merge_dict(base, override)
    assert merged["controls"]["opacity"] == {"kind": "slider", "show_as": "percent"}
    assert merged["controls"]["start"] == {"kind": "number"}


def test_merged_ui_spec_for_clip():
    generated = {
        "std-gradient": {
            "schema_version": 1,
            "controls": {"opacity": {"kind": "slider"}},
        }
    }
    overrides = {
        "std-gradient": {
            "controls": {"opacity": {"show_as": "percent"}},
        }
    }
    ui = merged_ui_spec_for_clip(generated, overrides, "std-gradient")
    assert ui is not None
    assert ui["controls"]["opacity"]["kind"] == "slider"
    assert ui["controls"]["opacity"]["show_as"] == "percent"


def test_extract_defaults_from_clip_class_gradient():
    from pixfabrica_std.background.gradient import Gradient

    defaults = extract_defaults_from_clip_class(Gradient)
    assert isinstance(defaults, dict)
    assert "opacity" in defaults
    assert defaults["opacity"] == 1.0


def test_to_json_safe_catalog_value_color():
    assert to_json_safe_catalog_value(Color("#AABBCC")) == "#AABBCC"


def test_extract_defaults_from_clip_class_sweep_lines():
    from pixfabrica_std.effects.sweep_lines import SweepLines

    defaults = extract_defaults_from_clip_class(SweepLines)
    assert defaults["color"] == "neutral"
    json.dumps(defaults)


def test_extract_defaults_from_json_schema():
    schema = {
        "properties": {
            "opacity": {"type": "number", "default": 1.0},
            "label": {"type": "string"},
            "enabled": {"type": "boolean", "default": True},
        }
    }
    defaults = extract_defaults_from_json_schema(schema)
    assert defaults == {"opacity": 1.0, "enabled": True}
