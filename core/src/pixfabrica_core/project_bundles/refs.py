"""Resolve local media paths and collect references in a web project document."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pixfabrica_core.catalog import CatalogCache
from pixfabrica_core.media_upload import resolve_media_path


@dataclass(frozen=True, slots=True)
class MediaRef:
    path_parts: tuple[str | int, ...]
    source_value: str


def is_remote_source(source: str) -> bool:
    return source.strip().startswith(("http://", "https://"))


def resolve_local_media_path(source: str, media_root: Path) -> Path | None:
    """Resolve a project source string to an existing local file, if any."""
    raw = source.strip()
    if not raw or is_remote_source(raw):
        return None

    normalized = raw.replace("\\", "/")
    candidates: list[str] = [raw]

    if "/media/" in normalized:
        candidates.append(normalized.rsplit("/media/", 1)[-1])

    path = Path(raw)
    if path.name and path.name not in candidates:
        candidates.append(path.name)

    root = media_root.resolve()
    direct = Path(raw)
    if direct.is_absolute():
        try:
            resolved = direct.resolve()
            if resolved.is_file():
                return resolved
        except OSError:
            pass

    for candidate in candidates:
        cleaned = candidate.replace("\\", "/").lstrip("/")
        if not cleaned or cleaned in {".", ".."}:
            continue
        try:
            resolved = resolve_media_path(root, cleaned).resolve()
        except ValueError:
            continue
        if resolved.is_file():
            return resolved
    return None


def file_fields_for_clip(catalog: CatalogCache, clip_type: str) -> list[str]:
    detail = catalog.details.get(clip_type)
    if detail is None:
        return ["source"]
    controls = detail.ui.get("controls")
    if not isinstance(controls, dict):
        return ["source"]
    fields = [
        field
        for field, spec in controls.items()
        if isinstance(spec, dict) and spec.get("kind") == "file"
    ]
    return fields or ["source"]


def collect_media_refs(
    project: dict[str, Any],
    catalog: CatalogCache,
    *,
    remote_only: bool = False,
) -> list[MediaRef]:
    refs: list[MediaRef] = []

    sounds = project.get("sounds")
    if isinstance(sounds, list):
        for index, sound in enumerate(sounds):
            if not isinstance(sound, dict):
                continue
            source = sound.get("source")
            if not isinstance(source, str) or not source.strip():
                continue
            remote = is_remote_source(source)
            if remote_only != remote:
                continue
            refs.append(MediaRef(("sounds", index, "source"), source))

    palette_source = project.get("palette_source")
    if isinstance(palette_source, dict) and palette_source.get("type") == "extracted":
        filename = palette_source.get("filename")
        if isinstance(filename, str) and filename.strip():
            remote = is_remote_source(filename)
            if remote_only == remote:
                refs.append(MediaRef(("palette_source", "filename"), filename))

    tracks = project.get("tracks")
    if isinstance(tracks, list):
        for track_index, track in enumerate(tracks):
            if not isinstance(track, dict):
                continue
            clips = track.get("clips")
            if not isinstance(clips, list):
                continue
            for clip_index, clip in enumerate(clips):
                if not isinstance(clip, dict):
                    continue
                clip_type = clip.get("clip_type")
                if not isinstance(clip_type, str) or not clip_type:
                    continue
                for field in file_fields_for_clip(catalog, clip_type):
                    value = clip.get(field)
                    if not isinstance(value, str) or not value.strip():
                        continue
                    remote = is_remote_source(value)
                    if remote_only != remote:
                        continue
                    refs.append(
                        MediaRef(
                            ("tracks", track_index, "clips", clip_index, field),
                            value,
                        )
                    )

    return refs


def set_json_value(project: dict[str, Any], path_parts: tuple[str | int, ...], value: str) -> None:
    cur: Any = project
    for part in path_parts[:-1]:
        cur = cur[part]
    cur[path_parts[-1]] = value
