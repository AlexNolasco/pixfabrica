"""Optional metadata describing how a job palette was chosen (web UI hint)."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from pixfabrica_core.theme.presets import ThemeName, ThemeVariant


class NamedPaletteSource(BaseModel):
    type: Literal["named"] = "named"
    theme: ThemeName
    variant: ThemeVariant


class ExtractedPaletteSource(BaseModel):
    type: Literal["extracted"] = "extracted"
    filename: str | None = None


class CustomPaletteSource(BaseModel):
    type: Literal["custom"] = "custom"


PaletteSource = Annotated[
    NamedPaletteSource | ExtractedPaletteSource | CustomPaletteSource,
    Field(discriminator="type"),
]
