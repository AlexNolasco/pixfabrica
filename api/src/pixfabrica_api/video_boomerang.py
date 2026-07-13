"""Build a forward+reverse (boomerang) video derivative via ffmpeg."""

from __future__ import annotations

import json
import logging
import math
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

log = logging.getLogger("pixfabrica.api.video_boomerang")

_MIN_LEG_SECONDS = 1e-3
_BOOMERANG_STEM_MARKER = ".boomerang-"


def is_boomerang_derivative_path(path: Path | str) -> bool:
    """True when path looks like output from create_boomerang_video."""
    return _BOOMERANG_STEM_MARKER in Path(path).stem


def reject_boomerang_derivative_source(path: Path | str) -> None:
    if is_boomerang_derivative_path(path):
        raise VideoTranscodeError("source is already a boomerang derivative")


@dataclass(frozen=True)
class BoomerangPlan:
    leg_source_seconds: float
    output_duration: float
    cycles: int
    capped: bool


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


def compute_boomerang_plan(
    *,
    source_duration: float,
    start_offset: float,
    playback_rate: float,
    max_duration: float,
    fps: float,
) -> BoomerangPlan:
    if source_duration <= 0:
        raise VideoTranscodeError("invalid source duration")
    if max_duration <= 0:
        raise VideoTranscodeError("invalid max duration")
    if playback_rate <= 0:
        raise VideoTranscodeError("playback_rate must be positive")

    playable_source = max(0.0, source_duration - max(0.0, start_offset))
    if playable_source <= _MIN_LEG_SECONDS:
        raise VideoTranscodeError("no playable video after start offset")

    one_leg_timeline = playable_source / playback_rate
    cycle_timeline = 2.0 * one_leg_timeline
    capped = cycle_timeline > max_duration + 1e-9

    if capped:
        cycles = 1
        leg_timeline = max_duration / 2.0
        leg_source = min(leg_timeline * playback_rate, playable_source)
        output_duration = _frame_floor(max_duration, fps)
    else:
        cycles = max(1, math.ceil(max_duration / cycle_timeline - 1e-9))
        leg_timeline = one_leg_timeline
        leg_source = playable_source
        output_duration = _frame_floor(cycles * cycle_timeline, fps)

    if leg_source <= _MIN_LEG_SECONDS or output_duration <= _MIN_LEG_SECONDS:
        raise VideoTranscodeError("boomerang output would be too short")

    return BoomerangPlan(
        leg_source_seconds=leg_source,
        output_duration=output_duration,
        cycles=cycles,
        capped=capped,
    )


def _build_boomerang_filter_graph(leg: float, cycles: int) -> str:
    if cycles < 1:
        raise VideoTranscodeError("boomerang cycle count must be positive")

    parts: list[str] = []
    labels: list[str] = []
    for index in range(cycles):
        parts.append(f"[0:v]trim=duration={leg:.6f},setpts=PTS-STARTPTS[fwd{index}];")
        parts.append(f"[0:v]trim=duration={leg:.6f},reverse,setpts=PTS-STARTPTS[rev{index}];")
        labels.append(f"[fwd{index}]")
        labels.append(f"[rev{index}]")

    stream_count = cycles * 2
    return "".join(parts) + "".join(labels) + f"concat=n={stream_count}:v=1:a=0[outv]"


def create_boomerang_video(
    source: Path,
    output: Path,
    *,
    start_offset: float,
    playback_rate: float,
    max_duration: float,
    target_fps: float,
) -> BoomerangPlan:
    if not ffmpeg_available():
        raise VideoTranscodeError("ffmpeg/ffprobe not available")
    if not source.is_file():
        raise VideoTranscodeError(f"source not found: {source}")
    reject_boomerang_derivative_source(source)

    source_duration = _probe_duration(source)
    plan = compute_boomerang_plan(
        source_duration=source_duration,
        start_offset=start_offset,
        playback_rate=playback_rate,
        max_duration=max_duration,
        fps=target_fps,
    )

    probe = probe_video(source)
    out_fps = min(probe.fps, target_fps, 60.0)
    gop = max(1, int(round(out_fps)))
    leg = plan.leg_source_seconds

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix="pixfabrica-boomerang-",
        suffix=".mp4",
        delete=False,
        dir=output.parent,
    ) as tmp:
        tmp_path = Path(tmp.name)

    filter_graph = _build_boomerang_filter_graph(leg, plan.cycles)

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
        "boomerang %s -> %s (planned %.3fs, actual %.3fs, leg %.3fs, cycles %d)",
        source.name,
        output.name,
        plan.output_duration,
        actual,
        leg,
        plan.cycles,
    )
    return plan
