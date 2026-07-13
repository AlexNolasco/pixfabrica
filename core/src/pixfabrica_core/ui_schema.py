"""UI schema helpers for plugin clip parameter models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field
from pydantic.fields import FieldInfo

StockMediaKind = Literal["image", "video"]
StockFieldRole = Literal["attribution", "provider"]


def _field_extra_dict(field_info: FieldInfo) -> dict[str, Any]:
    extra = field_info.json_schema_extra
    if isinstance(extra, dict):
        return extra
    return {}


def field_section_id(field_info: FieldInfo) -> str | None:
    """Return the custom Properties section id from ``json_schema_extra``, if any."""
    section = _field_extra_dict(field_info).get("section")
    if isinstance(section, str):
        stripped = section.strip()
        if stripped:
            return stripped
    return None


def field_stock_browse(field_info: FieldInfo) -> bool:
    """True when the param should expose Browse Stock in the file picker."""
    return _field_extra_dict(field_info).get("stock_browse") is True


def field_stock_media_kind(field_info: FieldInfo) -> StockMediaKind | None:
    """Return ``image`` or ``video`` for stock-browse file params."""
    kind = _field_extra_dict(field_info).get("stock_media")
    if kind in ("image", "video"):
        return kind
    return None


def field_stock_source_field(field_info: FieldInfo) -> str | None:
    """Return the paired source param name for stock attribution/provider fields."""
    src = _field_extra_dict(field_info).get("stock_source_field")
    if isinstance(src, str):
        stripped = src.strip()
        if stripped:
            return stripped
    return None


def field_stock_role(field_info: FieldInfo) -> StockFieldRole | None:
    """Return ``attribution`` or ``provider`` for stock metadata params."""
    role = _field_extra_dict(field_info).get("stock_role")
    if role in ("attribution", "provider"):
        return role
    return None


def section_field(section_id: str, /, **kwargs: Any) -> Any:
    """Declare a clip param that appears under a custom Properties section.

    All standard ``Field`` kwargs are supported (``default``, ``ge``, ``le``,
    ``multiple_of``, ``description``, …).

    Usage::

        room_width: float = section_field(
            "dimensions",
            default=8.0,
            ge=5.0,
            le=12.0,
            multiple_of=0.5,
            description="Room half-width in world units",
        )
    """
    stripped = section_id.strip()
    if not stripped:
        raise ValueError("section_id must be non-empty")

    extra = kwargs.pop("json_schema_extra", None) or {}
    if not isinstance(extra, dict):
        raise TypeError("json_schema_extra must be a dict when provided")

    return Field(json_schema_extra={**extra, "section": stripped}, **kwargs)


def stock_image_field(**kwargs: Any) -> Any:
    """Image file param that exposes Browse Stock in the editor."""
    extra = kwargs.pop("json_schema_extra", None) or {}
    if not isinstance(extra, dict):
        raise TypeError("json_schema_extra must be a dict when provided")
    return Field(
        json_schema_extra={**extra, "stock_browse": True, "stock_media": "image"},
        **kwargs,
    )


def stock_video_field(**kwargs: Any) -> Any:
    """Video file param that exposes Browse Stock in the editor."""
    extra = kwargs.pop("json_schema_extra", None) or {}
    if not isinstance(extra, dict):
        raise TypeError("json_schema_extra must be a dict when provided")
    return Field(
        json_schema_extra={**extra, "stock_browse": True, "stock_media": "video"},
        **kwargs,
    )


def stock_attribution_field(source_field: str, /, **kwargs: Any) -> Any:
    """Read-only stock attribution line paired with *source_field*."""
    stripped = source_field.strip()
    if not stripped:
        raise ValueError("source_field must be non-empty")
    extra = kwargs.pop("json_schema_extra", None) or {}
    if not isinstance(extra, dict):
        raise TypeError("json_schema_extra must be a dict when provided")
    kwargs.setdefault("default", "")
    kwargs.setdefault(
        "description",
        "Stock media attribution line (auto-filled on stock import)",
    )
    return Field(
        json_schema_extra={
            **extra,
            "stock_source_field": stripped,
            "stock_role": "attribution",
        },
        **kwargs,
    )


def stock_provider_field(source_field: str, /, **kwargs: Any) -> Any:
    """Hidden stock provider id paired with *source_field*."""
    stripped = source_field.strip()
    if not stripped:
        raise ValueError("source_field must be non-empty")
    extra = kwargs.pop("json_schema_extra", None) or {}
    if not isinstance(extra, dict):
        raise TypeError("json_schema_extra must be a dict when provided")
    kwargs.setdefault("default", "")
    kwargs.setdefault(
        "description",
        "Stock media provider id (auto-filled on stock import)",
    )
    return Field(
        json_schema_extra={
            **extra,
            "stock_source_field": stripped,
            "stock_role": "provider",
        },
        **kwargs,
    )
