"""Build merged font catalog from manifest + optional extra directory."""

from __future__ import annotations

from pathlib import Path

from pixfabrica_core.fonts.manifest import load_manifest
from pixfabrica_core.fonts.models import (
    FontFamilyEntry,
    FontManifest,
    FontWeightEntry,
    ManifestFamily,
)
from pixfabrica_core.fonts.paths import (
    default_bundled_fonts_dir,
    default_manifest_path,
    extra_fonts_dir,
    user_fonts_dir,
)
from pixfabrica_core.fonts.scan import scan_extra_fonts_dir

_PREVIEW_PREFIX = "/fonts/files"


def _family_from_manifest(
    family: ManifestFamily,
    _fonts_dir: Path,
    *,
    preview_url_prefix: str,
) -> FontFamilyEntry:
    weights: list[FontWeightEntry] = []
    for w in family.weights:
        woff2_name = Path(w.source).with_suffix(".woff2").name
        weights.append(
            FontWeightEntry(
                value=w.value,
                source=w.source,
                preview_url=f"{preview_url_prefix}/{woff2_name}",
            )
        )
    return FontFamilyEntry(
        id=family.id,
        family=family.family,
        label=family.label or family.family,
        category=family.category,
        weights=weights,
    )


def build_font_catalog(
    *,
    bundled_dir: Path | None = None,
    manifest_path: Path | None = None,
    user_dir: Path | None = None,
    extra_dir: Path | None = None,
    preview_url_prefix: str = _PREVIEW_PREFIX,
) -> list[FontFamilyEntry]:
    fonts_dir = (bundled_dir or default_bundled_fonts_dir()).resolve()
    manifest_file = manifest_path or default_manifest_path(fonts_dir)
    manifest = load_manifest(manifest_file)

    entries = [
        _family_from_manifest(f, fonts_dir, preview_url_prefix=preview_url_prefix)
        for f in manifest.families
    ]
    occupied_ids = frozenset(entry.id for entry in entries)

    resolved_user = (user_dir or user_fonts_dir()).resolve()
    if resolved_user.is_dir():
        entries.extend(
            scan_extra_fonts_dir(
                resolved_user,
                manifest_ids=occupied_ids,
                preview_url_prefix=preview_url_prefix,
            )
        )
        occupied_ids = frozenset(entry.id for entry in entries)

    resolved_extra = extra_dir if extra_dir is not None else extra_fonts_dir()
    if resolved_extra is not None:
        entries.extend(
            scan_extra_fonts_dir(
                resolved_extra.resolve(),
                manifest_ids=occupied_ids,
                preview_url_prefix=preview_url_prefix,
            )
        )

    return entries


def resolve_font_file(
    filename: str,
    *,
    bundled_dir: Path | None = None,
    user_dir: Path | None = None,
    extra_dir: Path | None = None,
) -> Path | None:
    """Resolve a catalog filename to an on-disk path (bundled, user, then extra dir)."""
    if not filename or "/" in filename or "\\" in filename or filename != Path(filename).name:
        return None
    if filename.startswith("."):
        return None

    fonts_dir = (bundled_dir or default_bundled_fonts_dir()).resolve()
    bundled_candidate = fonts_dir / filename
    if bundled_candidate.is_file() and not bundled_candidate.is_symlink():
        return bundled_candidate.resolve()

    user_root = (user_dir or user_fonts_dir()).resolve()
    user_candidate = user_root / filename
    if user_candidate.is_file() and not user_candidate.is_symlink():
        try:
            user_candidate.resolve().relative_to(user_root)
        except ValueError:
            return None
        return user_candidate.resolve()

    resolved_extra = extra_dir if extra_dir is not None else extra_fonts_dir()
    if resolved_extra is not None:
        extra_root = resolved_extra.resolve()
        extra_candidate = extra_root / filename
        if extra_candidate.is_file() and not extra_candidate.is_symlink():
            try:
                extra_candidate.resolve().relative_to(extra_root)
            except ValueError:
                return None
            return extra_candidate.resolve()

    return None


def iter_font_source_paths(
    manifest: FontManifest,
    fonts_dir: Path,
) -> list[tuple[str, Path]]:
    out: list[tuple[str, Path]] = []
    for family in manifest.families:
        for weight in family.weights:
            path = fonts_dir / weight.source
            out.append((weight.source, path))
    return out
