"""Load and validate bundled font manifest."""

from __future__ import annotations

import json
from pathlib import Path

from pixfabrica_core.fonts.models import FontManifest, ManifestFamily


class FontManifestError(ValueError):
    pass


def load_manifest(path: Path) -> FontManifest:
    if not path.is_file():
        raise FontManifestError(f"manifest not found: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise FontManifestError(f"invalid JSON in {path}: {exc}") from exc
    manifest = FontManifest.model_validate(raw)
    _validate_manifest(manifest, path.parent)
    return manifest


def _validate_manifest(manifest: FontManifest, fonts_dir: Path) -> None:
    seen_ids: set[str] = set()
    for family in manifest.families:
        if family.id in seen_ids:
            raise FontManifestError(f"duplicate family id: {family.id!r}")
        seen_ids.add(family.id)
        if not family.weights:
            raise FontManifestError(f"family {family.id!r} has no weights")
        seen_weights: set[int] = set()
        for weight in family.weights:
            if weight.value in seen_weights:
                raise FontManifestError(f"duplicate weight {weight.value} for family {family.id!r}")
            seen_weights.add(weight.value)
            source_path = fonts_dir / weight.source
            if source_path.suffix.lower() not in {".ttf", ".otf"}:
                raise FontManifestError(
                    f"manifest source must be .ttf or .otf, got {weight.source!r}"
                )


def manifest_families(manifest: FontManifest) -> list[ManifestFamily]:
    return list(manifest.families)
