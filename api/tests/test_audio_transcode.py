"""Tests for upload-time audio optimization."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from pixfabrica_api.audio_transcode import (
    allocate_unique_output_path,
    ffmpeg_available,
    optimize_audio_upload,
)


@pytest.fixture
def source_wav(tmp_path: Path) -> Path:
    if not ffmpeg_available():
        pytest.skip("ffmpeg required")
    out = tmp_path / "source.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1",
            "-c:a",
            "pcm_s16le",
            str(out),
        ],
        check=True,
        capture_output=True,
    )
    return out


def test_allocate_unique_output_path_suffix(tmp_path: Path):
    first = tmp_path / "song.m4a"
    first.write_bytes(b"a")
    second = allocate_unique_output_path(tmp_path / "song.m4a")
    assert second.name == "song-2.m4a"


def test_optimize_audio_upload_transcodes_to_m4a(source_wav: Path):
    result = optimize_audio_upload(source_wav)
    assert result.transcoded is True
    assert result.path.suffix == ".m4a"
    assert result.path.is_file()
    assert not source_wav.exists()
    assert result.optimized_for.format == "aac"
    assert result.optimized_for.bitrate_kbps == 192


def test_optimize_audio_upload_unique_collision(source_wav: Path):
    existing = source_wav.with_suffix(".m4a")
    existing.write_bytes(b"existing")
    result = optimize_audio_upload(source_wav)
    assert result.path.name == "source-2.m4a"
    assert existing.read_bytes() == b"existing"
