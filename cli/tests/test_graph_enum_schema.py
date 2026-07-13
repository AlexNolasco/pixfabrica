"""Tests for graph Enum / StrEnum annotation helpers."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel

from pixfabrica_cli.graph_enum_schema import enum_class_from_annotation, enum_wire_option_strings


class _Sample(StrEnum):
    A = "a"
    B = "b"


def test_enum_class_optional_wrapping():
    class M(BaseModel):
        x: _Sample | None = None

    assert enum_class_from_annotation(M.model_fields["x"].annotation) is _Sample


def test_enum_wire_option_strings_order():
    assert enum_wire_option_strings(_Sample) == ["a", "b"]
