"""Shared helpers for baking preview audio samples."""

from __future__ import annotations

import shutil
import subprocess
import warnings
from pathlib import Path

from pixfabrica_core.audio.analysis import (
    AnalyzerKind,
    AudioAnalyzerProtocol,
    get_analyzer,
    save_timeline_cache,
)
from pixfabrica_core.audio.preview_samples import (
    DEFAULT_BAKE_FPS,
    DEFAULT_BAKE_SECONDS,
    LOOP_LENGTH_OPTIONS,
    PREVIEW_SAMPLES_DIRNAME,
    SHIPPED_ANALYZER,
    PreviewSampleEntry,
    preview_samples_root,
    slugify_sample_id,
)


def export_audio_clip(source: Path, dest: Path, *, seek: float, duration: float) -> bool:
    if shutil.which("ffmpeg") is None:
        return False
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            str(seek),
            "-t",
            str(duration),
            "-i",
            str(source),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "44100",
            "-codec:a",
            "libmp3lame",
            "-q:a",
            "4",
            str(dest),
        ],
        check=True,
    )
    return True


def bake_one_sample(
    *,
    web_public: Path,
    source_path: Path,
    sample_id: str,
    label: str,
    seconds: float,
    fps: float = DEFAULT_BAKE_FPS,
    analyzer: AnalyzerKind = SHIPPED_ANALYZER,
    seek: float = 0.0,
    beat_tightness: float = 200.0,
    source_url: str = "",
    license_text: str = "",
    skip_audio: bool = False,
    analyzer_impl: AudioAnalyzerProtocol | None = None,
) -> PreviewSampleEntry:
    """Analyze, write ``{id}/timeline.npz`` + ``audio.mp3``, return manifest entry."""
    sid = slugify_sample_id(sample_id)
    sample_dir = preview_samples_root(web_public) / sid
    sample_dir.mkdir(parents=True, exist_ok=True)

    timeline_path = sample_dir / "timeline.npz"
    audio_path = sample_dir / "audio.mp3"

    impl = analyzer_impl or get_analyzer(analyzer)
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="divide by zero encountered in log10*",
            category=RuntimeWarning,
        )
        frames = impl.analyze(
            source_path.resolve(),
            seek=seek,
            duration=seconds,
            fps=fps,
            beat_tightness=beat_tightness,
        )
    save_timeline_cache(timeline_path, frames)

    if not skip_audio and not export_audio_clip(
        source_path, audio_path, seek=seek, duration=seconds
    ):
        warnings.warn("ffmpeg not found — skipped audio.mp3", stacklevel=2)

    base = f"/{PREVIEW_SAMPLES_DIRNAME}/{sid}"
    return PreviewSampleEntry(
        id=sid,
        label=label,
        seconds=seconds,
        fps=fps,
        analyzer=analyzer,
        audio=f"{base}/audio.mp3",
        timeline=f"{base}/timeline.npz",
        sourceUrl=source_url,
        license=license_text,
    )


def loop_lengths_to_bake(
    *,
    seconds: float | None,
    all_loops: bool,
) -> list[float]:
    if all_loops:
        return [float(s) for s in LOOP_LENGTH_OPTIONS]
    if seconds is not None:
        return [seconds]
    return [DEFAULT_BAKE_SECONDS]


def sample_id_for_duration(base_id: str, seconds: float, *, multiple_lengths: bool) -> str:
    sid = slugify_sample_id(base_id)
    if not multiple_lengths:
        return sid
    sec = int(seconds) if seconds == int(seconds) else seconds
    return f"{sid}-{sec}s"
