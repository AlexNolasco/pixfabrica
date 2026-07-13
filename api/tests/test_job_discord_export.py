"""Tests for Discord job export.

Fast unit tests cover bitrate math and planning. One short ffmpeg smoke test
proves the encode path; duration edge cases mock ffprobe duration so we do not
generate multi-minute fixture files.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from pixfabrica_api.job_discord_export import (
    MIN_VIDEO_BITRATE_K,
    DiscordExportTooLargeError,
    discord_export_filename,
    export_discord_video,
    fit_long_edge,
    long_edge_caps,
    plan_discord_export,
    size_budget,
    target_video_bitrate_k,
)
from pixfabrica_api.video_transcode import ffmpeg_available


def test_long_edge_caps_dedupes_and_descends():
    assert long_edge_caps(1920) == [1280, 854, 640, 480, 426]
    assert long_edge_caps(800) == [800, 640, 480, 426]
    assert long_edge_caps(480) == [480, 426]


def test_long_edge_caps_nitro_keeps_1080p():
    assert long_edge_caps(1920, max_mb=50) == [1920, 1280, 854, 640, 480, 426]


def test_fit_long_edge_preserves_aspect():
    w, h = fit_long_edge(1920, 1080, 1280)
    assert max(w, h) == 1280
    assert w % 2 == 0 and h % 2 == 0


def test_target_video_bitrate_accounts_for_audio():
    with_audio = target_video_bitrate_k(10.0, has_audio=True)
    without_audio = target_video_bitrate_k(10.0, has_audio=False)
    assert without_audio > with_audio


def test_target_video_bitrate_scales_with_cap():
    small = target_video_bitrate_k(60.0, has_audio=True, max_mb=8)
    large = target_video_bitrate_k(60.0, has_audio=True, max_mb=50)
    assert large > small


def test_discord_export_filename():
    assert discord_export_filename("My Viz", "id") == "My Viz-discord.mp4"
    assert discord_export_filename("My Viz", "id", max_mb=50) == "My Viz-discord-50mb.mp4"


def test_plan_discord_export_none_when_too_long():
    assert plan_discord_export(1920, 1080, 30.0, 900.0, has_audio=True) is None


def test_plan_discord_export_returns_plan_for_three_minute_clip():
    plan = plan_discord_export(1920, 1080, 30.0, 180.0, has_audio=True)
    assert plan is not None
    assert plan.video_bitrate_k > 0
    assert plan.video_bitrate_k < MIN_VIDEO_BITRATE_K
    assert max(plan.out_w, plan.out_h) <= 426


@pytest.fixture
def short_h264_mp4(tmp_path: Path) -> Path:
    if not ffmpeg_available():
        pytest.skip("ffmpeg/ffprobe required")
    out = tmp_path / "short.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=640x360:rate=24:duration=1",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            str(out),
        ],
        check=True,
        capture_output=True,
    )
    return out


@pytest.mark.ffmpeg
def test_export_discord_video_under_cap(short_h264_mp4: Path):
    max_bytes, _ = size_budget(8)
    export_path = export_discord_video(short_h264_mp4)
    try:
        assert export_path.is_file()
        assert export_path.stat().st_size <= max_bytes
    finally:
        export_path.unlink(missing_ok=True)


@pytest.mark.ffmpeg
def test_export_discord_video_under_tight_budget(
    short_h264_mp4: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Low target bitrate path without generating a multi-minute source file."""
    monkeypatch.setattr(
        "pixfabrica_api.job_discord_export._probe_duration",
        lambda _path: 180.0,
    )
    max_bytes, _ = size_budget(8)
    export_path = export_discord_video(short_h264_mp4)
    try:
        assert export_path.stat().st_size <= max_bytes
    finally:
        export_path.unlink(missing_ok=True)


def test_export_discord_video_rejects_impossible_duration(
    short_h264_mp4: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "pixfabrica_api.job_discord_export._probe_duration",
        lambda _path: 900.0,
    )
    with pytest.raises(DiscordExportTooLargeError):
        export_discord_video(short_h264_mp4)
