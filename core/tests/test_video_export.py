"""Tests for video export presets and encoder resolution."""

from __future__ import annotations

import pytest

from pixfabrica_core.video_export import (
    VideoEncoderUnavailableError,
    build_ffmpeg_video_encode_args,
    export_quality_profile,
    normalize_export_quality,
    resolve_video_codec_kind,
)


def test_normalize_export_quality_defaults_unknown_to_master():
    assert normalize_export_quality("nope") == "master"
    assert normalize_export_quality("draft") == "draft"


def test_master_profile_matches_legacy_defaults():
    profile = export_quality_profile("master")
    assert profile.pix_fmt == "yuv444p"
    assert profile.crf == 18
    assert profile.x264_preset == "medium"
    assert profile.x264_profile == "high444"


def test_build_ffmpeg_video_encode_args_cpu_master():
    args = build_ffmpeg_video_encode_args(export_quality="master", video_encoder="cpu")
    assert "-c:v" in args
    assert args[args.index("-c:v") + 1] == "libx264"
    assert "yuv444p" in args
    assert "18" in args


def test_build_ffmpeg_video_encode_args_cpu_draft():
    args = build_ffmpeg_video_encode_args(export_quality="draft", video_encoder="cpu")
    assert "yuv420p" in args
    assert "fast" in args
    assert "23" in args


def test_build_ffmpeg_video_encode_args_nvenc(monkeypatch):
    monkeypatch.setattr("pixfabrica_core.video_export.ffmpeg_has_h264_nvenc", lambda: True)
    args = build_ffmpeg_video_encode_args(export_quality="standard", video_encoder="nvenc")
    assert args[args.index("-c:v") + 1] == "h264_nvenc"
    assert "yuv420p" in args
    assert "20" in args


def test_resolve_video_codec_kind_nvenc_unavailable(monkeypatch):
    monkeypatch.setattr("pixfabrica_core.video_export.ffmpeg_has_h264_nvenc", lambda: False)
    with pytest.raises(VideoEncoderUnavailableError):
        resolve_video_codec_kind("nvenc")


def test_resolve_video_codec_kind_auto_falls_back_to_cpu(monkeypatch):
    monkeypatch.setattr("pixfabrica_core.video_export.ffmpeg_has_h264_nvenc", lambda: False)
    assert resolve_video_codec_kind("auto") == "libx264"
