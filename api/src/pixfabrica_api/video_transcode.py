"""Upload-time video optimization for API media uploads (ffmpeg/ffprobe)."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

log = logging.getLogger("pixfabrica.api.video_transcode")

# ── Tunable caps (v1 hard-coded) ─────────────────────────────────────────────
# Landscape 1080p bounds; portrait projects use long edge × short edge (1920×1080).
MAX_PROXY_WIDTH = 1920
MAX_PROXY_HEIGHT = 1080
MAX_PROXY_FPS = 30.0

_CAP_LONG = max(MAX_PROXY_WIDTH, MAX_PROXY_HEIGHT)
_CAP_SHORT = min(MAX_PROXY_WIDTH, MAX_PROXY_HEIGHT)

_H264_NAMES = frozenset({"h264", "avc1"})


class VideoTranscodeError(Exception):
    """Raised when probe or transcode fails."""


@dataclass(frozen=True)
class OptimizedFor:
    width: int
    height: int
    fps: float


@dataclass(frozen=True)
class VideoProbe:
    codec_name: str
    width: int
    height: int
    fps: float
    format_name: str


@dataclass(frozen=True)
class VideoOptimizeResult:
    path: Path
    optimized_for: OptimizedFor
    transcoded: bool


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _even(n: int) -> int:
    n = max(2, n)
    return n - (n % 2)


def _parse_fps(raw: str | None) -> float | None:
    if not raw or raw in {"0/0", "0"}:
        return None
    try:
        value = float(Fraction(raw))
    except (ValueError, ZeroDivisionError):
        return None
    return value if value > 0 else None


def _effective_max_box(
    target_width: int | None,
    target_height: int | None,
) -> tuple[int, int]:
    proj_w = target_width if target_width is not None else _CAP_LONG
    proj_h = target_height if target_height is not None else _CAP_SHORT
    if proj_h >= proj_w:
        return min(proj_w, _CAP_SHORT), min(proj_h, _CAP_LONG)
    return min(proj_w, _CAP_LONG), min(proj_h, _CAP_SHORT)


def _fit_dimensions(src_w: int, src_h: int, max_w: int, max_h: int) -> tuple[int, int]:
    if src_w <= max_w and src_h <= max_h:
        w, h = src_w, src_h
    else:
        scale = min(max_w / src_w, max_h / src_h)
        w = int(src_w * scale)
        h = int(src_h * scale)
    return _even(w), _even(h)


def _effective_fps(target_fps: float | None, source_fps: float) -> float:
    cap = target_fps if target_fps is not None else MAX_PROXY_FPS
    return min(source_fps, cap, MAX_PROXY_FPS)


def probe_video(path: Path) -> VideoProbe:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=codec_name,width,height,avg_frame_rate,r_frame_rate",
        "-show_entries",
        "format=format_name",
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

    streams = payload.get("streams") or []
    if not streams:
        raise VideoTranscodeError("no video stream found")

    stream = streams[0]
    width = int(stream.get("width") or 0)
    height = int(stream.get("height") or 0)
    if width <= 0 or height <= 0:
        raise VideoTranscodeError("invalid video dimensions")

    fps = _parse_fps(stream.get("avg_frame_rate")) or _parse_fps(stream.get("r_frame_rate"))
    if fps is None:
        fps = 30.0

    format_name = str((payload.get("format") or {}).get("format_name") or "")
    return VideoProbe(
        codec_name=str(stream.get("codec_name") or "").lower(),
        width=width,
        height=height,
        fps=fps,
        format_name=format_name.lower(),
    )


def _format_is_supported(format_name: str) -> bool:
    parts = {p.strip() for p in format_name.split(",") if p.strip()}
    return bool(parts & {"mp4", "mov", "m4a", "3gp", "3g2", "mj2"})


def needs_transcode(
    probe: VideoProbe,
    *,
    out_w: int,
    out_h: int,
    out_fps: float,
    source_path: Path,
) -> bool:
    ext = source_path.suffix.lower()
    if ext not in {".mp4", ".mov"}:
        return True
    if not _format_is_supported(probe.format_name):
        return True
    if probe.codec_name not in _H264_NAMES:
        return True
    if probe.width > out_w or probe.height > out_h:
        return True
    return probe.fps > out_fps + 0.05


def _run_ffmpeg(args: list[str]) -> None:
    try:
        proc = subprocess.run(args, capture_output=True, text=True, check=False)
    except OSError as exc:
        raise VideoTranscodeError("ffmpeg failed to start") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "ffmpeg failed").strip()
        raise VideoTranscodeError(detail)


def _transcode(source: Path, output: Path, *, out_w: int, out_h: int, out_fps: float) -> None:
    gop = max(1, int(round(out_fps)))
    scale = f"scale={out_w}:{out_h}"
    with tempfile.NamedTemporaryFile(
        prefix="pixfabrica-video-",
        suffix=".mp4",
        delete=False,
        dir=output.parent,
    ) as tmp:
        tmp_path = Path(tmp.name)

    try:
        _run_ffmpeg(
            [
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
                "fast",
                "-crf",
                "23",
                "-g",
                str(gop),
                "-keyint_min",
                str(gop),
                "-r",
                str(out_fps),
                "-c:a",
                "aac",
                "-b:a",
                "128k",
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


def optimize_video_upload(
    source: Path,
    *,
    target_width: int | None = None,
    target_height: int | None = None,
    target_fps: float | None = None,
) -> VideoOptimizeResult:
    """Return an render-friendly proxy, replacing *source* when transcoded."""
    if not ffmpeg_available():
        raise VideoTranscodeError("ffmpeg/ffprobe not available")

    probe = probe_video(source)
    max_w, max_h = _effective_max_box(target_width, target_height)
    out_w, out_h = _fit_dimensions(probe.width, probe.height, max_w, max_h)
    out_fps = _effective_fps(target_fps, probe.fps)

    if not needs_transcode(
        probe,
        out_w=out_w,
        out_h=out_h,
        out_fps=out_fps,
        source_path=source,
    ):
        return VideoOptimizeResult(
            path=source,
            optimized_for=OptimizedFor(width=probe.width, height=probe.height, fps=probe.fps),
            transcoded=False,
        )

    output = source.with_suffix(".mp4")
    _transcode(source, output, out_w=out_w, out_h=out_h, out_fps=out_fps)

    if output.resolve() != source.resolve() and source.exists():
        source.unlink()

    final_probe = probe_video(output)
    return VideoOptimizeResult(
        path=output,
        optimized_for=OptimizedFor(
            width=final_probe.width,
            height=final_probe.height,
            fps=final_probe.fps,
        ),
        transcoded=True,
    )
