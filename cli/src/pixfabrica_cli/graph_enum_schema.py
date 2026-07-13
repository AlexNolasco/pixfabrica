"""Detect Enum / StrEnum used on graph and config Pydantic models (CLI helpers)."""

from __future__ import annotations

import typing
from enum import Enum
from types import UnionType
from typing import Any, get_args, get_origin


def enum_class_from_annotation(annotation: Any) -> type[Enum] | None:
    """Return the Enum class if *annotation* is ``SomeEnum`` or ``SomeEnum | None``."""
    ann: Any = annotation
    origin = get_origin(ann)
    if origin is typing.Union or origin is UnionType:
        args = [a for a in get_args(ann) if a is not type(None)]
        if len(args) != 1:
            return None
        ann = args[0]

    if isinstance(ann, type) and issubclass(ann, Enum) and ann is not Enum:
        return ann
    return None


def enum_wire_option_strings(enum_cls: type[Enum]) -> list[str]:
    """Stable wire values for UI ``options`` (matches JSON job payloads)."""
    return [str(member.value) for member in enum_cls]
