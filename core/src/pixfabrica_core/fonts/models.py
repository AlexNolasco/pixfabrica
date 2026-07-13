"""Font catalog models (API + manifest)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

FontCategory = Literal["sans", "mono"]


class ManifestWeight(BaseModel):
    value: int = Field(ge=100, le=900)
    source: str = Field(description="Filename relative to bundled fonts dir (e.g. Inter-400.ttf)")


class ManifestFamily(BaseModel):
    id: str
    family: str
    label: str | None = None
    category: FontCategory
    weights: list[ManifestWeight]


class FontManifest(BaseModel):
    version: int = 1
    families: list[ManifestFamily]


class FontWeightEntry(BaseModel):
    value: int
    preview_url: str
    source: str


class FontFamilyEntry(BaseModel):
    id: str
    family: str
    label: str
    category: FontCategory
    weights: list[FontWeightEntry]
