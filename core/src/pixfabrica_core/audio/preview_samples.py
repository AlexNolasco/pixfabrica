"""Baked preview audio samples for clip preview (bus timelines + manifest)."""

from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import BaseModel, Field

from pixfabrica_core.audio.analysis import AnalyzerKind, load_timeline_cache
from pixfabrica_core.audio.bus import AudioBusFrame

MANIFEST_FILENAME = "manifest.json"
SOURCES_FILENAME = "sources.json"
PREVIEW_SAMPLES_DIRNAME = "preview-samples"
SOURCES_SUBDIR = "sources"
LOOP_LENGTH_OPTIONS = (8, 15, 45)
DEFAULT_BAKE_SECONDS = 45.0
DEFAULT_BAKE_FPS = 30.0
SHIPPED_ANALYZER = AnalyzerKind.STEM
DEFAULT_PREVIEW_SAMPLE_ID = "drums"


class PreviewSourceEntry(BaseModel):
    """Input catalog for ``bake-preview-samples`` (not served to the browser)."""

    id: str
    label: str
    file: str  # path relative to preview-samples/, e.g. sources/drums.mp3
    source_url: str = Field(alias="sourceUrl")
    license: str

    model_config = {"populate_by_name": True}


class PreviewSampleEntry(BaseModel):
    id: str
    label: str
    seconds: float
    fps: float
    analyzer: AnalyzerKind
    audio: str  # URL path, e.g. /preview-samples/drums/audio.mp3
    timeline: str  # URL path to timeline.npz
    source_url: str = Field(default="", alias="sourceUrl")
    license: str = ""

    model_config = {"populate_by_name": True}


class PreviewSamplesManifest(BaseModel):
    version: int = 1
    samples: list[PreviewSampleEntry] = Field(default_factory=list)


def slugify_sample_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "sample"


def preview_samples_root(web_public: Path) -> Path:
    return web_public / PREVIEW_SAMPLES_DIRNAME


def manifest_path(web_public: Path) -> Path:
    return preview_samples_root(web_public) / MANIFEST_FILENAME


def sources_path(web_public: Path) -> Path:
    return preview_samples_root(web_public) / SOURCES_FILENAME


def load_sources(web_public: Path) -> list[PreviewSourceEntry]:
    path = sources_path(web_public)
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "sources" in data:
        data = data["sources"]
    return [PreviewSourceEntry.model_validate(item) for item in data]


def load_manifest(web_public: Path) -> PreviewSamplesManifest:
    path = manifest_path(web_public)
    if not path.is_file():
        return PreviewSamplesManifest()
    data = json.loads(path.read_text(encoding="utf-8"))
    return PreviewSamplesManifest.model_validate(data)


def save_manifest(web_public: Path, manifest: PreviewSamplesManifest) -> None:
    root = preview_samples_root(web_public)
    root.mkdir(parents=True, exist_ok=True)
    manifest_path(web_public).write_text(
        manifest.model_dump_json(by_alias=True, indent=2),
        encoding="utf-8",
    )


def resolve_source_path(web_public: Path, source: PreviewSourceEntry) -> Path:
    root = preview_samples_root(web_public)
    return (root / source.file).resolve()


def entry_files(web_public: Path, entry: PreviewSampleEntry) -> tuple[Path, Path]:
    """Resolve manifest URL paths to on-disk audio and timeline files."""
    root = preview_samples_root(web_public)
    audio_rel = entry.audio.removeprefix("/").split(f"{PREVIEW_SAMPLES_DIRNAME}/", 1)[-1]
    timeline_rel = entry.timeline.removeprefix("/").split(f"{PREVIEW_SAMPLES_DIRNAME}/", 1)[-1]
    return root / audio_rel, root / timeline_rel


def load_entry_timeline(web_public: Path, entry: PreviewSampleEntry) -> list[AudioBusFrame]:
    _, timeline_path = entry_files(web_public, entry)
    if not timeline_path.is_file():
        return []
    return load_timeline_cache(timeline_path)


def fit_timeline_to_loop(
    frames: list[AudioBusFrame],
    *,
    loop_seconds: float,
    fps: float,
) -> list[AudioBusFrame]:
    target = max(1, int(round(loop_seconds * fps)))
    if len(frames) >= target:
        return frames[:target]
    return frames + [AudioBusFrame.zero() for _ in range(target - len(frames))]


def resample_timeline_fps(
    frames: list[AudioBusFrame],
    *,
    from_fps: float,
    to_fps: float,
    loop_seconds: float,
) -> list[AudioBusFrame]:
    if from_fps <= 0 or to_fps <= 0 or not frames:
        return fit_timeline_to_loop(frames, loop_seconds=loop_seconds, fps=to_fps)
    target = max(1, int(round(loop_seconds * to_fps)))
    out: list[AudioBusFrame] = []
    for i in range(target):
        t = i / to_fps
        src_i = min(int(t * from_fps), len(frames) - 1)
        out.append(frames[src_i])
    return out


def timeline_for_preview(
    frames: list[AudioBusFrame],
    *,
    baked_fps: float,
    loop_seconds: float,
    request_fps: float,
) -> list[AudioBusFrame]:
    if abs(baked_fps - request_fps) > 1e-6:
        frames = resample_timeline_fps(
            frames,
            from_fps=baked_fps,
            to_fps=request_fps,
            loop_seconds=loop_seconds,
        )
    return fit_timeline_to_loop(frames, loop_seconds=loop_seconds, fps=request_fps)


def find_web_public(start: Path | None = None) -> Path:
    start = (start or Path.cwd()).resolve()
    for base in (start, *start.parents):
        candidate = base / "web" / "public"
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError(f"web/public not found from {start}")


def verify_shipped_samples(web_public: Path) -> list[str]:
    """Return list of problems (empty if the checked-in bundle is complete)."""
    issues: list[str] = []
    sources = load_sources(web_public)
    if not sources:
        issues.append(f"missing or empty {SOURCES_FILENAME}")
        return issues

    manifest = load_manifest(web_public)
    by_id = {s.id: s for s in manifest.samples}
    for src in sources:
        entry = by_id.get(src.id)
        if entry is None:
            issues.append(f"manifest missing sample id={src.id!r}")
            continue
        audio_path, timeline_path = entry_files(web_public, entry)
        if not timeline_path.is_file():
            issues.append(f"missing timeline: {timeline_path}")
        if not audio_path.is_file():
            issues.append(f"missing audio: {audio_path}")
    return issues
