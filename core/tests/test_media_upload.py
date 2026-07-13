"""Tests for media upload helpers."""

from __future__ import annotations

import pytest

from pixfabrica_core.clips import ClipCategory
from pixfabrica_core.media_upload import (
    is_lossless_audio_filename,
    kind_for_clip_category,
    kind_for_extension,
    max_bytes_for_audio_upload,
    max_bytes_for_kind,
    resolve_media_path,
    sanitize_upload_basename,
)


def test_kind_for_clip_category_lyrics():
    assert kind_for_clip_category(ClipCategory.LYRICS) == "lyrics"
    assert kind_for_clip_category(ClipCategory.IMAGE) == "image"


def test_sanitize_upload_basename():
    assert sanitize_upload_basename(r"C:\music\song.wav") == "song.wav"
    assert sanitize_upload_basename("../etc/passwd") == "passwd"
    with pytest.raises(ValueError):
        sanitize_upload_basename("")
    with pytest.raises(ValueError):
        sanitize_upload_basename("..")


def test_resolve_media_path_blocks_escape(tmp_path):
    root = tmp_path / "media"
    root.mkdir()
    dest = resolve_media_path(root, "song.wav")
    assert dest.parent == root.resolve()


def test_kind_for_extension():
    assert kind_for_extension("track.lrc") == "lyrics"
    assert kind_for_extension("photo.png") == "image"


def test_max_bytes_for_kind():
    assert max_bytes_for_kind("lyrics") < max_bytes_for_kind("video")


def test_is_lossless_audio_filename():
    assert is_lossless_audio_filename("track.wav")
    assert is_lossless_audio_filename("TRACK.FLAC")
    assert not is_lossless_audio_filename("track.mp3")


def test_max_bytes_for_audio_upload():
    assert max_bytes_for_audio_upload("song.wav") > max_bytes_for_audio_upload("song.mp3")
    assert max_bytes_for_audio_upload("song.mp3") == max_bytes_for_kind("audio")
