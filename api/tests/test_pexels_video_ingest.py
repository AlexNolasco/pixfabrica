"""Tests for Pexels video ingest file selection."""

from __future__ import annotations

from pixfabrica_api.pexels_video_ingest import (
    is_pexels_video_file_url,
    select_pexels_video_file,
)


def test_is_pexels_video_file_url_accepts_vimeo_cdn():
    assert is_pexels_video_file_url(
        "https://player.vimeo.com/external/342571552.hd.mp4?s=abc&profile_id=175"
    )


def test_select_prefers_largest_under_target():
    files = [
        {
            "link": "https://player.vimeo.com/external/1.sd.mp4",
            "width": 640,
            "height": 360,
            "size": 1000,
        },
        {
            "link": "https://player.vimeo.com/external/2.hd.mp4",
            "width": 1280,
            "height": 720,
            "size": 5000,
        },
        {
            "link": "https://player.vimeo.com/external/3.uhd.mp4",
            "width": 1920,
            "height": 1080,
            "size": 9000,
        },
    ]
    selected = select_pexels_video_file(files, target_width=1920, target_height=1080)
    assert selected is not None
    assert selected["link"] == files[2]["link"]


def test_select_smallest_above_when_none_fit():
    files = [
        {
            "link": "https://player.vimeo.com/external/1.hd.mp4",
            "width": 2560,
            "height": 1440,
            "size": 8000,
        },
        {
            "link": "https://player.vimeo.com/external/2.uhd.mp4",
            "width": 3840,
            "height": 2160,
            "size": 20000,
        },
    ]
    selected = select_pexels_video_file(files, target_width=1920, target_height=1080)
    assert selected is not None
    assert selected["link"] == files[0]["link"]
