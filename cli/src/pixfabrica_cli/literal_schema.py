"""Literal[...] wire values and NLS / UI key helpers (CLI)."""

from __future__ import annotations

import typing
from types import UnionType
from typing import Any, get_args, get_origin


def literal_wire_slug(value: Any) -> str:
    """Stable slug segment for a literal wire value (used in NLS / UI keys)."""
    s = str(value).strip().lower()
    return s.replace(" ", "_").replace("-", "_").replace(".", "_")


def literal_label_key_prefix(
    type_id: str | None, field_name: str, *, catalog_kind: str = "clip"
) -> str:
    """Prefix for per-option keys: ``{prefix}.{slug(wire)}``."""
    if type_id:
        return f"{catalog_kind}.{type_id}.field.{field_name}.option"
    return f"literal.field.{field_name}.option"


def literal_tuple_from_annotation(annotation: Any) -> tuple[Any, ...] | None:
    """If *annotation* is ``Literal[...]`` or ``Optional[Literal[...]]``, return the values tuple."""
    ann: Any = annotation
    origin = get_origin(ann)
    if origin is typing.Union or origin is UnionType:
        args = [a for a in get_args(ann) if a is not type(None)]
        if len(args) != 1:
            return None
        ann = args[0]
        origin = get_origin(ann)
    if origin is not None and getattr(origin, "__name__", "") == "Literal":
        return get_args(ann)
    return None


def literal_display_en(value: Any) -> str:
    """Default English label for a literal value (title-like words)."""
    s = str(value)
    return " ".join(w.capitalize() for w in s.replace("-", " ").split())
