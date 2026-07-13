from __future__ import annotations

import logging
import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, GetCoreSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import core_schema

_log = logging.getLogger("pixfabrica.theme")


class ColorToken(StrEnum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    TERTIARY = "tertiary"
    ACCENT = "accent"
    BACKGROUND = "background"
    NEUTRAL = "neutral"
    NEUTRAL_VARIANT = "neutral_variant"


HEX_RE = re.compile(r"^#([0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


class Color:
    def __init__(self, value: str):
        if not HEX_RE.match(value):
            raise ValueError(f"Invalid color: {value}")

        self.hex = value
        self.rgba = self._parse(value)  # normalized 0.0-1.0, for ModernGL and skia.Color4f

    def _parse(self, value: str) -> tuple[float, float, float, float]:
        value = value.lstrip("#")
        if len(value) == 6:
            return (
                int(value[0:2], 16) / 255.0,
                int(value[2:4], 16) / 255.0,
                int(value[4:6], 16) / 255.0,
                1.0,
            )
        return (
            int(value[0:2], 16) / 255.0,
            int(value[2:4], 16) / 255.0,
            int(value[4:6], 16) / 255.0,
            int(value[6:8], 16) / 255.0,
        )

    def __repr__(self):
        return f"Color({self.hex})"

    def __str__(self):
        return self.hex

    @classmethod
    def __get_pydantic_core_schema__(cls, _source_type: Any, _handler: GetCoreSchemaHandler):
        def validate(v):
            if isinstance(v, cls):
                return v
            if isinstance(v, str):
                return cls(v)
            raise TypeError(f"Invalid type for Color: {type(v)}")

        return core_schema.no_info_plain_validator_function(
            validate,
            serialization=core_schema.to_string_ser_schema(),
        )

    @classmethod
    def __get_pydantic_json_schema__(
        cls, _core_schema: core_schema.CoreSchema, _handler: Any
    ) -> JsonSchemaValue:
        return {
            "type": "string",
            "pattern": r"^#([0-9a-fA-F]{6}|[0-9a-fA-F]{8})$",
            "examples": ["#FFFFFF"],
        }


def color_field(token: ColorToken, **kwargs: Any) -> Any:
    """Declare a themed color field.

    The field default is the token itself (e.g. ColorToken.NEUTRAL). At draw
    time clips call resolve_color(self.color, ctx.job.colors) to get a Color.
    Users can override with a literal Color hex — resolve_color passes it through.

    An explicit default= kwarg takes precedence over the token (supports
    clips that haven't migrated to ColorToken | Color yet).

    Usage::

        color: ColorToken | Color = color_field(ColorToken.BACKGROUND)
    """
    default = kwargs.pop("default", token)
    return Field(default=default, json_schema_extra={"widget": "color"}, **kwargs)


def resolve_color(v: ColorToken | Color, palette: ColorPalette) -> Color:
    """Resolve a token reference or literal Color against a palette.

    If v is a ColorToken, returns the matching slot from palette.
    If v is a literal Color, returns it unchanged (palette bypassed).
    """
    if isinstance(v, ColorToken):
        color = getattr(palette, v, None)
        if color is None:
            _log.warning("color token %r not in palette, falling back to primary", v)
            return palette.primary
        return color
    return v


class ColorPalette(BaseModel):
    model_config = ConfigDict(frozen=True)

    primary: Color = Color("#6200EE")
    secondary: Color = Color("#03DAC6")
    tertiary: Color = Color("#018786")
    accent: Color = Color("#BB86FC")
    background: Color = Color("#121212")
    neutral: Color = Color("#FFFFFF")
    neutral_variant: Color = Color("#E0E0E0")
