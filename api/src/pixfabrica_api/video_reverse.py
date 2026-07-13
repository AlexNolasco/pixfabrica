"""Build a reversed video derivative via ffmpeg."""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from pixfabrica_api.video_transcode import (
    VideoTranscodeError,
    _run_ffmpeg,
    ffmpeg_available,
    probe_video,
)

log = logging.getLogger("pixfabrica.api.video_reverse")

_MIN_SECONDS = 1e-3


@dataclass(frozen=True)
class ReversePlan:
    source_seconds: float
    output_duration: float


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


def _frame_floor(seconds: float, fps: float) -> float:
    min_sec = 1.0 / fps
    if seconds <= 0:
        return min_sec
    return max(min_sec, float(int(seconds * fps)) / fps)


def compute_reverse_plan(
    *,
    source_duration: float,
    start_offset: float,
    playback_rate: float,
    fps: float,
) -> ReversePlan:
    if source_duration <= 0:
        raise VideoTranscodeError("invalid source duration")
    if playback_rate <= 0:
        raise VideoTranscodeError("playback_rate must be positive")

    playable_source = max(0.0, source_duration - max(0.0, start_offset))
    if playable_source <= _MIN_SECONDS:
        raise VideoTranscodeError("no playable video after start offset")

    output_duration = _frame_floor(playable_source / playback_rate, fps)
    if output_duration <= _MIN_SECONDS:
        raise VideoTranscodeError("reverse output would be too short")

    return ReversePlan(
        source_seconds=playable_source,
        output_duration=output_duration,
    )


def create_reversed_video(
    source: Path,
    output: Path,
    *,
    start_offset: float,
    playback_rate: float,
    target_fps: float,
) -> ReversePlan:
    if not ffmpeg_available():
        raise VideoTranscodeError("ffmpeg/ffprobe not available")
    if not source.is_file():
        raise VideoTranscodeError(f"source not found: {source}")

    source_duration = _probe_duration(source)
    plan = compute_reverse_plan(
        source_duration=source_duration,
        start_offset=start_offset,
        playback_rate=playback_rate,
        fps=target_fps,
    )

    probe = probe_video(source)
    out_fps = min(probe.fps, target_fps, 60.0)
    gop = max(1, int(round(out_fps)))
    leg = plan.source_seconds

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix="pixfabrica-reverse-",
        suffix=".mp4",
        delete=False,
        dir=output.parent,
    ) as tmp:
        tmp_path = Path(tmp.name)

    filter_graph = (
        f"[0:v]trim=duration={leg:.6f},setpts=PTS-STARTPTS,reverse,setpts=PTS-STARTPTS[outv]"
    )

    try:
        _run_ffmpeg(
            [
                "ffmpeg",
                "-y",
                "-ss",
                f"{max(0.0, start_offset):.6f}",
                "-i",
                str(source),
                "-filter_complex",
                filter_graph,
                "-map",
                "[outv]",
                "-an",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-preset",
                "fast",
                "-crf",
                "23",
                "-g",
                str(gop),
                "-keyint_min",
                str(gop),
                "-r",
                str(out_fps),
                "-movflags",
                "+faststart",
                str(tmp_path),
            ]
        )
        if output.exists():
            output.unlink()
        tmp_path.replace(output)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    actual = _probe_duration(output)
    log.debug(
        "reverse %s -> %s (planned %.3fs, actual %.3fs, leg %.3fs)",
        source.name,
        output.name,
        plan.output_duration,
        actual,
        leg,
    )
    return plan
