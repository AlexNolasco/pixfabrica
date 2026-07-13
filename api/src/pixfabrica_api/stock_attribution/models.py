"""Shared provenance payload for stock media apply requests."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

MediaKind = Literal["photo", "video"]


class StockProvenance(BaseModel):
    provider: str = Field(min_length=1, max_length=64)
    page_url: str = Field(min_length=1, max_length=2048)
    creator_name: str = Field(min_length=1, max_length=512)
    creator_url: str | None = Field(default=None, max_length=2048)
    media_kind: MediaKind | None = None
    extras: dict[str, Any] | None = None
