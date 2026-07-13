"""Tests for UI schema helpers."""

from __future__ import annotations

from pydantic import BaseModel

from pixfabrica_core.ui_schema import (
    field_section_id,
    field_stock_browse,
    field_stock_media_kind,
    field_stock_role,
    field_stock_source_field,
    section_field,
    stock_attribution_field,
    stock_image_field,
    stock_provider_field,
    stock_video_field,
)


def test_section_field_merges_json_schema_extra():
    class M(BaseModel):
        tint: str = section_field(
            "appearance",
            default="#ffffff",
            json_schema_extra={"widget": "color"},
        )

    finfo = M.model_fields["tint"]
    assert field_section_id(finfo) == "appearance"
    assert finfo.json_schema_extra == {"widget": "color", "section": "appearance"}


def test_stock_image_field_metadata():
    class M(BaseModel):
        wall_source: str | None = stock_image_field(default=None)

    finfo = M.model_fields["wall_source"]
    assert field_stock_browse(finfo) is True
    assert field_stock_media_kind(finfo) == "image"


def test_stock_video_field_metadata():
    class M(BaseModel):
        source: str = stock_video_field(default="")

    finfo = M.model_fields["source"]
    assert field_stock_browse(finfo) is True
    assert field_stock_media_kind(finfo) == "video"


def test_stock_attribution_pair_metadata():
    class M(BaseModel):
        wall_source: str | None = stock_image_field(default=None)
        wall_source_attribution: str = stock_attribution_field("wall_source")
        wall_source_provider: str = stock_provider_field("wall_source")

    attr = M.model_fields["wall_source_attribution"]
    prov = M.model_fields["wall_source_provider"]
    assert field_stock_role(attr) == "attribution"
    assert field_stock_role(prov) == "provider"
    assert field_stock_source_field(attr) == "wall_source"
    assert field_stock_source_field(prov) == "wall_source"


def test_section_field_rejects_empty_id():
    try:
        section_field("   ")
    except ValueError as exc:
        assert "non-empty" in str(exc)
    else:
        raise AssertionError("expected ValueError")
