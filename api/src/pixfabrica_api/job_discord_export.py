"""On-demand Discord export for completed render jobs (ffmpeg)."""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pixfabrica_api.video_transcode import (
    VideoTranscodeError,
    _even,
    _run_ffmpeg,
    ffmpeg_available,
    probe_video,
)

log = logging.getLogger("pixfabrica.api.job_discord_export")

DiscordExportMaxMb = Literal[8, 50]
DISCORD_EXPORT_MAX_MB_CHOICES: frozenset[int] = frozenset({8, 50})
DEFAULT_MAX_MB: DiscordExportMaxMb = 8

LONG_EDGE_CAPS_STANDARD = (1280, 854, 640, 480, 426)
LONG_EDGE_CAPS_NITRO = (1920, 1280, 854, 640, 480, 426)

AUDIO_BITRATE_K = 96
MIN_VIDEO_BITRATE_K = 400
MIN_VIDEO_BITRATE_FLOOR_K = 120
MAX_BITRATE_RETRIES = 5


class DiscordExportError(Exception):
    """Base error for Discord export failures."""


class DiscordExportTooLargeError(DiscordExportError):
    """Video cannot be compressed under the Discord size cap."""


@dataclass(frozen=True)
class DiscordExportPlan:
    out_w: int
    out_h: int
    out_fps: float
    video_bitrate_k: int
    has_audio: bool


def normalize_max_mb(value: int) -> DiscordExportMaxMb:
    if value in DISCORD_EXPORT_MAX_MB_CHOICES:
        return value  # type: ignore[return-value]
    return DEFAULT_MAX_MB


def size_budget(max_mb: int) -> tuple[int, int]:
    """Return (max_bytes, target_bytes) for a Discord upload cap."""
    cap = normalize_max_mb(max_mb)
    max_bytes = cap * 1024 * 1024
    target_bytes = int(max_bytes * (7.5 / 8.0))
    return max_bytes, target_bytes


def _probe_duration(path: Path) -> float:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except OSError as exc:
        raise VideoTranscodeError("ffprobe failed to start") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "ffprobe failed").strip()
        raise VideoTranscodeError(detail)
    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise VideoTranscodeError("ffprobe returned invalid JSON") from exc
    duration = float((payload.get("format") or {}).get("duration") or 0)
    if duration <= 0:
        raise VideoTranscodeError("invalid video duration")
    return duration


def _has_audio_stream(path: Path) -> bool:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=codec_type",
        "-of",
        "json",
        str(path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except OSError:
        return False
    if proc.returncode != 0:
        return False
    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return False
    return bool(payload.get("streams"))


def long_edge_caps(source_long: int, *, max_mb: int = DEFAULT_MAX_MB) -> list[int]:
    ladder = LONG_EDGE_CAPS_NITRO if normalize_max_mb(max_mb) >= 50 else LONG_EDGE_CAPS_STANDARD
    seen: set[int] = set()
    caps: list[int] = []
    for cap in ladder:
        edge = min(source_long, cap)
        if edge not in seen:
            seen.add(edge)
            caps.append(edge)
    return caps


def fit_long_edge(src_w: int, src_h: int, max_long: int) -> tuple[int, int]:
    long_edge = max(src_w, src_h)
    if long_edge <= max_long:
        return _even(src_w), _even(src_h)
    scale = max_long / long_edge
    return _even(int(src_w * scale)), _even(int(src_h * scale))


def target_video_bitrate_k(
    duration_s: float,
    *,
    has_audio: bool,
    max_mb: int = DEFAULT_MAX_MB,
) -> int:
    _max_bytes, target_bytes = size_budget(max_mb)
    target_bits = target_bytes * 8
    audio_bits = (AUDIO_BITRATE_K * 1000 * duration_s) if has_audio else 0.0
    video_bits = max(0.0, target_bits - audio_bits)
    return max(0, int(video_bits / duration_s / 1000))


def plan_discord_export(
    source_w: int,
    source_h: int,
    source_fps: float,
    duration_s: float,
    *,
    has_audio: bool,
    max_mb: int = DEFAULT_MAX_MB,
) -> DiscordExportPlan | None:
    """Return the preferred plan, or None when no positive video bitrate is available."""
    video_k = target_video_bitrate_k(duration_s, has_audio=has_audio, max_mb=max_mb)
    if video_k <= 0:
        return None
    source_long = max(source_w, source_h)
    max_long = long_edge_caps(source_long, max_mb=max_mb)[-1]
    out_w, out_h = fit_long_edge(source_w, source_h, max_long)
    return DiscordExportPlan(
        out_w=out_w,
        out_h=out_h,
        out_fps=source_fps,
        video_bitrate_k=video_k,
        has_audio=has_audio,
    )


def _transcode_discord(source: Path, output: Path, plan: DiscordExportPlan) -> None:
    gop = max(1, int(round(plan.out_fps)))
    scale = f"scale={plan.out_w}:{plan.out_h}"
    maxrate_k = max(plan.video_bitrate_k + 1, int(plan.video_bitrate_k * 1.08))
    bufsize_k = max(plan.video_bitrate_k * 2, maxrate_k * 2)
    args = [
        "ffmpeg",
        "-y",
        "-i",
        str(source),
        "-vf",
        scale,
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-preset",
        "veryfast",
        "-b:v",
        f"{plan.video_bitrate_k}k",
        "-maxrate",
        f"{maxrate_k}k",
        "-bufsize",
        f"{bufsize_k}k",
        "-g",
        str(gop),
        "-keyint_min",
        str(gop),
        "-r",
        str(plan.out_fps),
        "-movflags",
        "+faststart",
    ]
    if plan.has_audio:
        args.extend(["-c:a", "aac", "-b:a", f"{AUDIO_BITRATE_K}k"])
    else:
        args.append("-an")
    args.append(str(output))
    _run_ffmpeg(args)


def export_discord_video(source: Path, *, max_mb: int = DEFAULT_MAX_MB) -> Path:
    """Transcode *source* to a temp file sized for a Discord upload cap."""
    if not ffmpeg_available():
        raise VideoTranscodeError("ffmpeg/ffprobe not available")

    cap_mb = normalize_max_mb(max_mb)
    max_bytes, _target_bytes = size_budget(cap_mb)

    probe = probe_video(source)
    duration_s = _probe_duration(source)
    has_audio = _has_audio_stream(source)
    source_long = max(probe.width, probe.height)
    base_video_k = target_video_bitrate_k(duration_s, has_audio=has_audio, max_mb=cap_mb)
    if base_video_k <= 0:
        raise DiscordExportTooLargeError(
            f"Video is too long ({duration_s:.1f}s) to fit Discord's {cap_mb} MB upload limit."
        )

    caps = long_edge_caps(source_long, max_mb=cap_mb)
    last_size: int | None = None

    for max_long in caps:
        out_w, out_h = fit_long_edge(probe.width, probe.height, max_long)
        video_k = base_video_k

        for attempt in range(MAX_BITRATE_RETRIES):
            plan = DiscordExportPlan(
                out_w=out_w,
                out_h=out_h,
                out_fps=probe.fps,
                video_bitrate_k=max(video_k, 1),
                has_audio=has_audio,
            )
            with tempfile.NamedTemporaryFile(
                prefix="pixfabrica-discord-",
                suffix=".mp4",
                delete=False,
            ) as tmp:
                tmp_path = Path(tmp.name)
            try:
                _transcode_discord(source, tmp_path, plan)
                size = tmp_path.stat().st_size
                last_size = size
                if size <= max_bytes:
                    log.info(
                        "discord export ok cap=%dMB size=%d plan=%dx%d@%dk attempt=%d",
                        cap_mb,
                        size,
                        plan.out_w,
                        plan.out_h,
                        plan.video_bitrate_k,
                        attempt + 1,
                    )
                    return tmp_path
                tmp_path.unlink(missing_ok=True)
            except Exception:
                tmp_path.unlink(missing_ok=True)
                raise

            video_k = int(video_k * 0.85)
            if video_k < MIN_VIDEO_BITRATE_FLOOR_K:
                break

    detail = (
        f"Video is too long ({duration_s:.1f}s) to fit Discord's {cap_mb} MB upload limit"
        f" (last attempt was {last_size / (1024 * 1024):.1f} MB)."
        if last_size is not None
        else f"Video is too long ({duration_s:.1f}s) to fit Discord's {cap_mb} MB upload limit."
    )
    raise DiscordExportTooLargeError(detail)


def discord_export_filename(title: str, job_id: str, *, max_mb: int = DEFAULT_MAX_MB) -> str:
    cap_mb = normalize_max_mb(max_mb)
    base = (title or job_id).replace("/", "-")
    if cap_mb == 8:
        return f"{base}-discord.mp4"
    return f"{base}-discord-{cap_mb}mb.mp4"
