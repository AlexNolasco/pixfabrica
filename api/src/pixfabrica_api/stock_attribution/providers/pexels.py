"""Pexels attribution formatting."""

from __future__ import annotations

from pixfabrica_api.stock_attribution.models import StockProvenance


def format_attribution(provenance: StockProvenance) -> str | None:
    if provenance.provider != "pexels":
        return None
    creator = provenance.creator_name.strip()
    page_url = provenance.page_url.strip()
    if not creator or not page_url:
        return None
    kind = provenance.media_kind or "photo"
    label = "Video" if kind == "video" else "Photo"
    return f"{label} by {creator} on Pexels: {page_url}"
