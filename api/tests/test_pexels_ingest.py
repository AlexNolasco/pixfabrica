"""Tests for Pexels ingest URL selection."""

from __future__ import annotations

from pixfabrica_api.pexels_ingest import is_pexels_media_url, pexels_ingest_url_candidates


def test_is_pexels_media_url():
    assert is_pexels_media_url("https://images.pexels.com/photos/1/a.jpg")
    assert not is_pexels_media_url("https://example.com/a.jpg")


def test_ingest_candidates_portrait():
    src = {
        "portrait": "https://images.pexels.com/photos/1/portrait.jpg",
        "large": "https://images.pexels.com/photos/1/large.jpg",
        "original": "https://images.pexels.com/photos/1/original.jpg",
    }
    assert pexels_ingest_url_candidates(src, "portrait") == [
        src["portrait"],
        src["large"],
        src["original"],
    ]


def test_ingest_candidates_landscape():
    src = {
        "landscape": "https://images.pexels.com/photos/1/landscape.jpg",
        "large": "https://images.pexels.com/photos/1/large.jpg",
        "original": "https://images.pexels.com/photos/1/original.jpg",
    }
    assert pexels_ingest_url_candidates(src, "landscape")[0] == src["landscape"]
