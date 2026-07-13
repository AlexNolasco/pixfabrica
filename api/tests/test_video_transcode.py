"""Tests for upload-time video optimization."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from pixfabrica_api.video_transcode import (
    MAX_PROXY_HEIGHT,
    MAX_PROXY_WIDTH,
    ffmpeg_available,
    needs_transcode,
    optimize_video_upload,
    probe_video,
)


@pytest.fixture
def source_1080p60(tmp_path: Path) -> Path:
    if not ffmpeg_available():
        pytest.skip("ffmpeg/ffprobe required")
    out = tmp_path / "source.mov"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=1920x1080:rate=60:duration=1",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-g",
            "60",
            str(out),
        ],
        check=True,
        capture_output=True,
    )
    return out


@pytest.fixture
def source_640x360_24(tmp_path: Path) -> Path:
    if not ffmpeg_available():
        pytest.skip("ffmpeg/ffprobe required")
    out = tmp_path / "small.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=640x360:rate=24:duration=1",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-g",
            "24",
            str(out),
        ],
        check=True,
        capture_output=True,
    )
    return out


def test_probe_video_reads_dimensions(source_1080p60: Path):
    probe = probe_video(source_1080p60)
    assert probe.width == 1920
    assert probe.height == 1080
    assert probe.codec_name == "h264"
    assert probe.fps == pytest.approx(60.0, rel=0.05)


def test_needs_transcode_large_source(source_1080p60: Path):
    probe = probe_video(source_1080p60)
    assert needs_transcode(
        probe,
        out_w=640,
        out_h=360,
        out_fps=24.0,
        source_path=source_1080p60,
    )


def test_skip_small_h264_mp4(source_640x360_24: Path):
    probe = probe_video(source_640x360_24)
    assert not needs_transcode(
        probe,
        out_w=640,
        out_h=360,
        out_fps=24.0,
        source_path=source_640x360_24,
    )


def test_optimize_downscales_to_project_target(source_1080p60: Path):
    result = optimize_video_upload(
        source_1080p60,
        target_width=640,
        target_height=360,
        target_fps=24.0,
    )
    assert result.transcoded is True
    assert result.path.suffix == ".mp4"
    assert not source_1080p60.exists()
    probe = probe_video(result.path)
    assert probe.width <= 640
    assert probe.height <= 360
    assert probe.fps <= 24.1


def test_optimize_skips_when_already_small(source_640x360_24: Path):
    result = optimize_video_upload(
        source_640x360_24,
        target_width=1280,
        target_height=720,
        target_fps=30.0,
    )
    assert result.transcoded is False
    assert result.path == source_640x360_24
    assert result.optimized_for.width == 640
    assert result.optimized_for.height == 360
    assert result.optimized_for.fps == pytest.approx(24.0)


def test_hard_cap_limits_target(source_1080p60: Path):
    result = optimize_video_upload(
        source_1080p60,
        target_width=3840,
        target_height=2160,
        target_fps=60.0,
    )
    probe = probe_video(result.path)
    assert probe.width <= MAX_PROXY_WIDTH
    assert probe.height <= MAX_PROXY_HEIGHT
    assert probe.fps <= 30.1


def test_portrait_project_keeps_full_height(source_1080p60: Path, tmp_path: Path):
    if not ffmpeg_available():
        pytest.skip("ffmpeg/ffprobe required")
    portrait = tmp_path / "portrait.mov"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=2160x3840:rate=30:duration=1",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-g",
            "30",
            str(portrait),
        ],
        check=True,
        capture_output=True,
    )
    result = optimize_video_upload(
        portrait,
        target_width=1080,
        target_height=1920,
        target_fps=30.0,
    )
    probe = probe_video(result.path)
    assert probe.width == 1080
    assert probe.height == 1920
