"""Upload-time lossless audio optimization for API media uploads (ffmpeg)."""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from pixfabrica_core.media_upload import is_lossless_audio_filename

log = logging.getLogger("pixfabrica.api.audio_transcode")

AAC_BITRATE = "192k"


class AudioTranscodeError(Exception):
    """Raised when transcode fails."""


@dataclass(frozen=True)
class AudioOptimizedFor:
    format: str
    bitrate_kbps: int


@dataclass(frozen=True)
class AudioOptimizeResult:
    path: Path
    optimized_for: AudioOptimizedFor
    transcoded: bool


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def allocate_unique_output_path(base: Path) -> Path:
    """Return *base* when free, else ``stem-2.ext``, ``stem-3.ext``, …"""
    if not base.exists():
        return base
    stem = base.stem
    suffix = base.suffix
    parent = base.parent
    n = 2
    while True:
        candidate = parent / f"{stem}-{n}{suffix}"
        if not candidate.exists():
            return candidate
        n += 1


def _run_ffmpeg(args: list[str]) -> None:
    try:
        proc = subprocess.run(args, capture_output=True, text=True, check=False)
    except OSError as exc:
        raise AudioTranscodeError("ffmpeg failed to start") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "ffmpeg failed").strip()
        raise AudioTranscodeError(detail)


def _transcode_to_aac(source: Path, output: Path) -> None:
    with tempfile.NamedTemporaryFile(
        prefix="pixfabrica-audio-",
        suffix=".m4a",
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
                "-vn",
                "-c:a",
                "aac",
                "-b:a",
                AAC_BITRATE,
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


def optimize_audio_upload(source: Path) -> AudioOptimizeResult:
    """Transcode lossless uploads to AAC .m4a and remove the source file."""
    if not is_lossless_audio_filename(source.name):
        raise AudioTranscodeError("not a lossless audio upload")
    if not ffmpeg_available():
        raise AudioTranscodeError("ffmpeg not available")

    output = allocate_unique_output_path(source.with_suffix(".m4a"))
    _transcode_to_aac(source, output)

    if source.exists():
        source.unlink()

    return AudioOptimizeResult(
        path=output,
        optimized_for=AudioOptimizedFor(format="aac", bitrate_kbps=192),
        transcoded=True,
    )
