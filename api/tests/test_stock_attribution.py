"""Tests for stock attribution registry."""

from __future__ import annotations

from pixfabrica_api.stock_attribution import StockProvenance, format_stock_attribution


def test_pexels_photo_attribution():
    provenance = StockProvenance(
        provider="pexels",
        page_url="https://www.pexels.com/photo/42/",
        creator_name="Jane Doe",
        media_kind="photo",
    )
    assert format_stock_attribution(provenance) == (
        "Photo by Jane Doe on Pexels: https://www.pexels.com/photo/42/",
        "pexels",
    )


def test_pexels_video_attribution():
    provenance = StockProvenance(
        provider="pexels",
        page_url="https://www.pexels.com/video/99/",
        creator_name="Alex Kim",
        media_kind="video",
    )
    assert format_stock_attribution(provenance) == (
        "Video by Alex Kim on Pexels: https://www.pexels.com/video/99/",
        "pexels",
    )


def test_unknown_provider_returns_none():
    provenance = StockProvenance(
        provider="unknown",
        page_url="https://example.com/item",
        creator_name="Someone",
    )
    assert format_stock_attribution(provenance) is None


def test_civitai_stub_returns_none():
    provenance = StockProvenance(
        provider="civitai",
        page_url="https://civitai.com/videos/1",
        creator_name="Maker",
        media_kind="video",
        extras={"model_name": "Example"},
    )
    assert format_stock_attribution(provenance) is None
