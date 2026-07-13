"""Bus timeline NPZ sidecars for portable project bundles."""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pixfabrica_core.audio.analysis import AnalyzerKind
from pixfabrica_core.audio.cache import timeline_cache_path_for_file

ANALYSIS_DIR = "analysis"
_SIDECAR_SAFE = re.compile(r"[^\w\-]+")


@dataclass(frozen=True, slots=True)
class SoundAnalysisSpec:
    sound_id: str
    asset_rel: str
    local_path: Path
    seek: float
    duration: float | None
    fps: float
    beat_tightness: float

    def cache_path(self, cache_dir: Path) -> Path:
        return timeline_cache_path_for_file(
            cache_dir,
            self.local_path,
            self.seek,
            self.duration,
            self.fps,
            self.beat_tightness,
        )

    def sidecar_zip_path(self) -> str:
        safe_id = _SIDECAR_SAFE.sub("_", self.sound_id.strip()) or "sound"
        return f"{ANALYSIS_DIR}/{safe_id}_{AnalyzerKind.STEM.value}.npz"

    def manifest_entry(self, sidecar_rel: str) -> dict[str, Any]:
        return {
            "sound_id": self.sound_id,
            "asset": self.asset_rel,
            "sidecar": sidecar_rel,
            "analyzer": AnalyzerKind.STEM.value,
            "seek": self.seek,
            "duration": self.duration,
            "fps": self.fps,
            "beat_tightness": self.beat_tightness,
        }


def default_cache_dir() -> Path:
    _tmp = Path(tempfile.gettempdir())
    return Path(os.environ.get("PIXFABRICA_CACHE_DIR", str(_tmp / "pixfabrica_cache")))


def sound_analysis_specs_for_bundled_sounds(
    project: dict[str, Any],
    sound_asset_paths: dict[int, tuple[Path, str]],
) -> list[SoundAnalysisSpec]:
    """Build analysis specs for sounds mapped to ``(host_path, assets/... rel)``."""
    sounds = project.get("sounds")
    if not isinstance(sounds, list):
        return []

    fps_raw = project.get("fps")
    fps = float(fps_raw) if isinstance(fps_raw, (int, float)) and fps_raw else 30.0

    specs: list[SoundAnalysisSpec] = []
    for index, sound in enumerate(sounds):
        if not isinstance(sound, dict):
            continue
        paths = sound_asset_paths.get(index)
        if paths is None:
            continue
        local_path, asset_rel = paths
        sound_id = sound.get("id")
        if not isinstance(sound_id, str) or not sound_id.strip():
            continue

        seek = float(sound.get("seek") or 0.0)
        duration_raw = sound.get("duration")
        duration = float(duration_raw) if isinstance(duration_raw, (int, float)) else None
        beat = float(sound.get("beat_tightness") or 200.0)

        specs.append(
            SoundAnalysisSpec(
                sound_id=sound_id,
                asset_rel=asset_rel,
                local_path=local_path,
                seek=seek,
                duration=duration,
                fps=fps,
                beat_tightness=beat,
            )
        )
    return specs


def collect_analysis_sidecars_for_export(
    specs: list[SoundAnalysisSpec],
    *,
    cache_dir: Path,
) -> tuple[list[dict[str, Any]], list[tuple[str, Path]]]:
    """Manifest rows and ``(zip_path, host_npz_path)`` for cache hits only."""
    manifest: list[dict[str, Any]] = []
    files: list[tuple[str, Path]] = []

    for spec in specs:
        cache_file = spec.cache_path(cache_dir)
        if not cache_file.is_file():
            continue
        sidecar = spec.sidecar_zip_path()
        manifest.append(spec.manifest_entry(sidecar))
        files.append((sidecar, cache_file))

    return manifest, files


def hydrate_analysis_cache_from_manifest(
    manifest_analysis: object,
    *,
    bundle_dir: Path,
    cache_dir: Path,
    sidecar_bytes: dict[str, bytes],
) -> int:
    """Copy bundled NPZ sidecars into the host analysis cache. Returns count hydrated."""
    if not isinstance(manifest_analysis, list):
        return 0

    hydrated = 0
    cache_dir.mkdir(parents=True, exist_ok=True)

    for raw in manifest_analysis:
        if not isinstance(raw, dict):
            continue
        asset = raw.get("asset")
        sidecar = raw.get("sidecar")
        seek = float(raw.get("seek") or 0.0)
        duration_raw = raw.get("duration")
        duration = float(duration_raw) if isinstance(duration_raw, (int, float)) else None
        fps = float(raw.get("fps") or 30.0)
        beat = float(raw.get("beat_tightness") or 200.0)

        if not isinstance(asset, str) or not isinstance(sidecar, str):
            continue
        npz = sidecar_bytes.get(sidecar)
        if not npz:
            continue

        if not asset.startswith("assets/"):
            continue
        rel = asset[len("assets/") :]
        from pixfabrica_core.media_upload import resolve_media_path

        try:
            audio_path = resolve_media_path(bundle_dir, rel)
        except ValueError:
            continue
        if not audio_path.is_file():
            continue

        dest = timeline_cache_path_for_file(
            cache_dir,
            audio_path,
            seek,
            duration,
            fps,
            beat,
        )
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(npz)
        hydrated += 1

    return hydrated
