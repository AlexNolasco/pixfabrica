"""Video export quality presets and FFmpeg encoder resolution."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from typing import Literal

ExportQuality = Literal["draft", "standard", "master"]
VideoEncoder = Literal["auto", "cpu", "nvenc"]
VideoCodecKind = Literal["libx264", "h264_nvenc"]

_COLOR_TAGS: tuple[str, ...] = (
    "-colorspace",
    "bt709",
    "-color_primaries",
    "bt709",
    "-color_trc",
    "bt709",
    "-color_range",
    "pc",
)


@dataclass(frozen=True)
class ExportQualityProfile:
    pix_fmt: str
    crf: int
    x264_preset: str
    x264_profile: str
    nvenc_preset: str


_EXPORT_QUALITY_PROFILES: dict[ExportQuality, ExportQualityProfile] = {
    "draft": ExportQualityProfile(
        pix_fmt="yuv420p",
        crf=23,
        x264_preset="fast",
        x264_profile="high",
        nvenc_preset="p1",
    ),
    "standard": ExportQualityProfile(
        pix_fmt="yuv420p",
        crf=20,
        x264_preset="medium",
        x264_profile="high",
        nvenc_preset="p4",
    ),
    "master": ExportQualityProfile(
        pix_fmt="yuv444p",
        crf=18,
        x264_preset="medium",
        x264_profile="high444",
        nvenc_preset="p6",
    ),
}


class VideoEncoderUnavailableError(RuntimeError):
    """Raised when the requested hardware encoder is not available."""


def normalize_export_quality(value: str) -> ExportQuality:
    if value in _EXPORT_QUALITY_PROFILES:
        return value  # type: ignore[return-value]
    return "master"


def normalize_video_encoder(value: str) -> VideoEncoder:
    if value in ("auto", "cpu", "nvenc"):
        return value  # type: ignore[return-value]
    return "auto"


def export_quality_profile(quality: str) -> ExportQualityProfile:
    return _EXPORT_QUALITY_PROFILES[normalize_export_quality(quality)]


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def ffmpeg_has_h264_nvenc() -> bool:
    if not ffmpeg_available():
        return False
    try:
        proc = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return False
    return "h264_nvenc" in (proc.stdout or "")


def resolve_video_codec_kind(encoder: str) -> VideoCodecKind:
    requested = normalize_video_encoder(encoder)
    if requested == "cpu":
        return "libx264"
    if requested == "nvenc":
        if not ffmpeg_has_h264_nvenc():
            raise VideoEncoderUnavailableError(
                "h264_nvenc is not available — NVIDIA GPU and FFmpeg NVENC support required"
            )
        return "h264_nvenc"
    return "h264_nvenc" if ffmpeg_has_h264_nvenc() else "libx264"


def build_ffmpeg_video_encode_args(
    *,
    export_quality: str,
    video_encoder: str,
) -> list[str]:
    """FFmpeg video encode flags (after filters, before ``-movflags``)."""
    profile = export_quality_profile(export_quality)
    codec = resolve_video_codec_kind(video_encoder)

    if codec == "libx264":
        return [
            "-c:v",
            "libx264",
            "-profile:v",
            profile.x264_profile,
            "-preset",
            profile.x264_preset,
            "-pix_fmt",
            profile.pix_fmt,
            "-crf",
            str(profile.crf),
            *_COLOR_TAGS,
        ]

    # NVENC does not support yuv444p in typical builds — use 420 at same CQ tier.
    return [
        "-c:v",
        "h264_nvenc",
        "-preset",
        profile.nvenc_preset,
        "-tune",
        "hq",
        "-rc",
        "vbr",
        "-cq",
        str(profile.crf),
        "-pix_fmt",
        "yuv420p",
        "-profile:v",
        "high",
        *_COLOR_TAGS,
    ]
