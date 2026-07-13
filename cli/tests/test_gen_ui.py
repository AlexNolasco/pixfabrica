"""Tests for plugin gen-ui inference helpers."""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, Field

from pixfabrica_cli.commands.gen_ui import (
    _build_controls_for_class,
    _build_sections,
    _infer_from_json_schema_property,
    _infer_from_model_field,
    _ui_entry_for_type_class,
)
from pixfabrica_core.media_upload import max_bytes_for_kind
from pixfabrica_std.background.gradient import Gradient
from pixfabrica_std.common import FitMode
from pixfabrica_std.effects.palette_cycle_gl import PaletteCycle
from pixfabrica_std.image.background_image import BackgroundImage


def test_track_card_typography_roles_use_typography_picker():
    from pixfabrica_std.player.track_card import TrackCard

    controls, unknowns, _ = _build_controls_for_class(TrackCard)
    assert unknowns == []
    assert controls["title_typography_role"]["kind"] == "typography_role"
    assert controls["author_typography_role"]["kind"] == "typography_role"


def test_static_text_typography_role_uses_typography_picker():
    from pixfabrica_std.text.static_text import StaticText

    controls, unknowns, _ = _build_controls_for_class(StaticText)
    assert unknowns == []
    assert controls["typography_role"]["kind"] == "typography_role"


def test_source_field_uses_file_control():
    from pixfabrica_std.image.background_image import BackgroundImage

    controls, unknowns, _ = _build_controls_for_class(BackgroundImage)
    assert unknowns == []
    src = controls["source"]
    assert src["kind"] == "file"
    assert src["upload_kind"] == "image"
    assert ".png" in src["accept"]
    assert src["max_bytes"] == max_bytes_for_kind("image")


def test_angle_full_rotation_uses_rotation_slider():
    class M(BaseModel):
        angle: float = Field(default=0.0, ge=-360.0, le=360.0, multiple_of=1.0)

    controls, unknowns, _ = _build_controls_for_class(M)
    assert unknowns == []
    assert controls["angle"] == {
        "kind": "slider",
        "show_as": "rotation",
        "minimum": -360.0,
        "maximum": 360.0,
        "presets": [-90, -45, -15, -5, 0, 5, 15, 45, 90],
        "step": 1.0,
    }


def test_angle_band_uses_rotation_slider():
    class M(BaseModel):
        angle: float = Field(
            default=0.0,
            ge=-90.0,
            le=90.0,
            multiple_of=1.0,
            description="Tilt in degrees; positive tilts up left→right",
        )

    controls, unknowns, _ = _build_controls_for_class(M)
    assert unknowns == []
    assert controls["angle"] == {
        "kind": "slider",
        "show_as": "rotation",
        "minimum": -90.0,
        "maximum": 90.0,
        "presets": [-90, -45, -15, -5, 0, 5, 15, 45, 90],
        "step": 1.0,
    }


def test_rotation_uses_rotation_slider():
    class M(BaseModel):
        rotation: float = Field(default=0.0, ge=0.0, le=360.0, multiple_of=1.0)

    controls, unknowns, _ = _build_controls_for_class(M)
    assert unknowns == []
    assert controls["rotation"] == {
        "kind": "slider",
        "show_as": "rotation",
        "minimum": 0.0,
        "maximum": 360.0,
        "presets": [0, 5, 15, 45, 90],
        "step": 1.0,
    }


def test_json_schema_rotation():
    prop = {"type": "number", "minimum": 0.0, "maximum": 360.0}
    assert _infer_from_json_schema_property("rotation", prop) == {
        "kind": "slider",
        "show_as": "rotation",
        "minimum": 0.0,
        "maximum": 360.0,
        "presets": [0, 5, 15, 45, 90],
        "step": 1.0,
    }


def test_json_schema_angle():
    prop = {"type": "number", "minimum": -90.0, "maximum": 90.0}
    assert _infer_from_json_schema_property("angle", prop) == {
        "kind": "slider",
        "show_as": "rotation",
        "minimum": -90.0,
        "maximum": 90.0,
        "presets": [-90, -45, -15, -5, 0, 5, 15, 45, 90],
        "step": 1.0,
    }


def test_angle_presets_clamped_to_field_range():
    prop = {"type": "number", "minimum": -89.0, "maximum": 89.0}
    assert _infer_from_json_schema_property("angle", prop) == {
        "kind": "slider",
        "show_as": "rotation",
        "minimum": -89.0,
        "maximum": 89.0,
        "presets": [-45, -15, -5, 0, 5, 15, 45],
        "step": 1.0,
    }


def test_offset_y_uses_anchor_slider():
    class M(BaseModel):
        offset_y: float = Field(default=0.5, ge=0.0, le=1.0, multiple_of=0.1)

    controls, unknowns, _ = _build_controls_for_class(M)
    assert unknowns == []
    assert controls["offset_y"] == {
        "kind": "slider",
        "show_as": "anchor",
        "axis": "y",
        "step": 0.1,
    }


def test_offset_x_uses_anchor_slider():
    class M(BaseModel):
        offset_x: float = Field(default=0.5, ge=0.0, le=1.0)

    controls, unknowns, _ = _build_controls_for_class(M)
    assert unknowns == []
    assert controls["offset_x"]["show_as"] == "anchor"
    assert controls["offset_x"]["axis"] == "x"


def test_json_schema_offset_y_anchor():
    prop = {"type": "number", "minimum": 0.0, "maximum": 1.0}
    assert _infer_from_json_schema_property("offset_y", prop) == {
        "kind": "slider",
        "show_as": "anchor",
        "axis": "y",
    }


def test_json_schema_slider_percent():
    prop = {"type": "number", "minimum": 0.0, "maximum": 1.0}
    assert _infer_from_json_schema_property("opacity", prop) == {
        "kind": "slider",
        "show_as": "percent",
    }


def test_multiple_of_overrides_percent_default_step():

    class M(BaseModel):
        clip_type: ClassVar[str] = "test"
        wobble: float = Field(default=0.2, ge=0.0, le=1.0, multiple_of=0.1)

    controls, unknowns, warnings = _build_controls_for_class(M)
    assert unknowns == []
    assert controls["wobble"]["show_as"] == "percent"
    assert controls["wobble"]["step"] == 0.1
    assert warnings == []


def test_attach_step_on_slider_percent():
    class M(BaseModel):
        opacity: float = Field(default=0.5, ge=0.0, le=1.0)

    controls, unknowns, warnings = _build_controls_for_class(M)
    assert unknowns == []
    assert controls["opacity"]["step"] == 0.01
    assert warnings == []


def test_model_field_literal_segmented():
    class M(BaseModel):
        align: Literal["left", "center", "right"] = "center"

    finfo = M.model_fields["align"]
    r = _infer_from_model_field("align", finfo, None)
    assert r["kind"] == "segmented_enum"
    assert set(r["options"]) == {"left", "center", "right"}
    assert r["label_key_prefix"] == "literal.field.align.option"


def test_model_field_bus_select():
    class M(BaseModel):
        bus_select: str | None = None

    finfo = M.model_fields["bus_select"]
    assert _infer_from_model_field("bus_select", finfo, None) == {"kind": "bus_select"}


def test_build_controls_hybrid_prefers_json_when_valid():
    class M(BaseModel):
        x: float = Field(default=0.5, ge=0.0, le=1.0)

    controls, unknowns, _ = _build_controls_for_class(M)
    assert unknowns == []
    assert controls["x"]["kind"] == "slider"
    assert controls["x"]["step"] == 0.01


def test_gradient_color_stops_color_stop_list():
    controls, unknowns, _ = _build_controls_for_class(Gradient)
    assert "color_stops" in controls
    assert "color_stops" not in unknowns
    cs = controls["color_stops"]
    assert cs["kind"] == "color_stop_list"
    assert cs["min_items"] == 2
    assert "ColorStop" in cs["item_model"]
    assert cs["item_fields"]["color"]["kind"] == "theme_or_color"
    assert cs["item_fields"]["position"]["kind"] == "slider"


def test_palette_cycle_palette_color_list():
    controls, unknowns, _ = _build_controls_for_class(PaletteCycle)
    assert "palette" in controls
    assert "palette" not in unknowns
    pl = controls["palette"]
    assert pl["kind"] == "color_list"
    assert pl["min_items"] == 0
    assert pl["max_items"] == 8
    assert "PaletteSwatch" in pl["item_model"]
    assert pl["item_fields"]["color"]["kind"] == "theme_or_color"


def test_gradient_direction_literal_prefix():
    controls, _, _ = _build_controls_for_class(Gradient)
    d = controls["direction"]
    assert d["kind"] == "select"
    assert d["label_key_prefix"] == "clip.std-gradient.field.direction.option"
    assert "to bottom" in d["options"]


def test_clip_id_control_hidden_readonly():
    controls, _, _ = _build_controls_for_class(Gradient)
    assert controls["id"] == {"kind": "hidden", "read_only": True}
    sections = _build_sections("std-gradient", Gradient)
    for sec in sections:
        assert "id" not in sec["fields"]


def test_stock_attribution_controls():
    controls, unknowns, step_warnings = _build_controls_for_class(BackgroundImage)
    assert unknowns == []
    assert controls["source"]["stock_browse"] is True
    assert controls["source_attribution"] == {
        "kind": "textarea",
        "rows": 3,
        "read_only": True,
        "stock_source_field": "source",
    }
    assert controls["source_provider"] == {
        "kind": "hidden",
        "read_only": True,
        "stock_source_field": "source",
    }
    _, _, _, ui_warnings = _ui_entry_for_type_class(BackgroundImage)
    assert not any("stock browse enabled" in w for w in ui_warnings)
    sections = _build_sections("std-background-image", BackgroundImage)
    param_fields = sections[0]["fields"]
    assert param_fields.index("source_attribution") == len(param_fields) - 1
    assert "source_provider" not in param_fields


def test_stock_browse_without_attribution_warns():
    from pixfabrica_core.ui_schema import stock_image_field

    class IncompleteStockNode(BaseModel):
        clip_type: ClassVar[str] = "std-incomplete-stock"

        texture: str | None = stock_image_field(default=None)

    _, _, _, warnings = _ui_entry_for_type_class(IncompleteStockNode)
    assert len(warnings) == 1
    assert "texture: stock browse enabled" in warnings[0]
    assert "stock_attribution_field('texture')" in warnings[0]
    assert "stock_provider_field('texture')" in warnings[0]


def test_stock_browse_partial_attribution_warns():
    from pixfabrica_core.ui_schema import stock_attribution_field, stock_image_field

    class PartialStockNode(BaseModel):
        clip_type: ClassVar[str] = "std-partial-stock"

        texture: str | None = stock_image_field(default=None)
        texture_attribution: str = stock_attribution_field("texture")

    _, _, _, warnings = _ui_entry_for_type_class(PartialStockNode)
    assert len(warnings) == 1
    assert "stock_provider_field('texture')" in warnings[0]
    assert "stock_attribution_field" not in warnings[0]


def test_model_field_strenum_fitmode():
    class M(BaseModel):
        fit: FitMode = FitMode.COVER

    finfo = M.model_fields["fit"]
    r = _infer_from_model_field("fit", finfo, None)
    assert r["kind"] == "segmented_enum"
    assert r["label_key_prefix"] == "enum.FitMode"
    assert set(r["options"]) == {m.value for m in FitMode}


def test_build_sections_custom_section():
    from pixfabrica_core.ui_schema import section_field

    class M(BaseModel):
        alpha: float = Field(default=1.0, ge=0.0, le=1.0)
        mesh: str = section_field("model_3d", default="skull", description="Bundled glTF asset")
        mesh_color: str = section_field("model_3d", default="#ffffff")
        beta: float = Field(default=0.5)
        start: float = 0.0
        duration: float = 1.0
        enabled: bool = True

    sections = _build_sections("std-example", M, catalog_kind="clip")
    assert [s["id"] for s in sections] == ["parameters", "model_3d", "timing"]
    assert sections[0]["title_key"] == "ui.clip.std-example.section.parameters"
    assert sections[0]["fields"] == ["alpha", "beta"]
    assert sections[1]["title_key"] == "ui.clip.std-example.section.model_3d"
    assert sections[1]["fields"] == ["mesh", "mesh_color"]
    assert sections[2]["fields"] == ["start", "duration", "enabled"]


def test_section_field_preserves_constraints():
    from pixfabrica_core.ui_schema import field_section_id, section_field

    class M(BaseModel):
        room_width: float = section_field(
            "dimensions",
            default=8.0,
            ge=5.0,
            le=12.0,
            multiple_of=0.5,
            description="Room half-width in world units",
        )

    finfo = M.model_fields["room_width"]
    assert field_section_id(finfo) == "dimensions"
    assert finfo.metadata  # ge/le/multiple_of live in metadata
    controls, unknowns, _ = _build_controls_for_class(M)
    assert unknowns == []
    assert controls["room_width"]["kind"] == "slider"
    assert controls["room_width"]["minimum"] == 5.0
    assert controls["room_width"]["maximum"] == 12.0
    assert controls["room_width"]["step"] == 0.5
