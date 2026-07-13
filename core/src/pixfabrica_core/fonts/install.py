"""Install upright font sources into the user fonts directory."""

from __future__ import annotations

import io
import logging
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from pixfabrica_core.fonts.build import _compress_ttf_to_woff2
from pixfabrica_core.fonts.manifest import load_manifest
from pixfabrica_core.fonts.paths import (
    default_bundled_fonts_dir,
    default_manifest_path,
    is_allowed_font_path,
    user_fonts_dir,
    woff2_path_for_source,
)
from pixfabrica_core.fonts.scan import _slugify, read_font_metadata
from pixfabrica_core.media_upload import sanitize_upload_basename

log = logging.getLogger("pixfabrica_core.fonts.install")

_SOURCE_SUFFIXES = frozenset({".ttf", ".otf"})


@dataclass
class FontInstallResult:
    installed_count: int = 0
    families: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.installed_count > 0


def _is_safe_zip_name(name: str) -> bool:
    path = PurePosixPath(name)
    if path.is_absolute():
        return False
    return ".." not in path.parts


def _manifest_family_ids() -> frozenset[str]:
    fonts_dir = default_bundled_fonts_dir()
    manifest_path = default_manifest_path(fonts_dir)
    if not manifest_path.is_file():
        return frozenset()
    manifest = load_manifest(manifest_path)
    return frozenset(family.id for family in manifest.families)


def _collect_sources_from_upload(data: bytes, filename: str) -> list[Path]:
    suffix = Path(filename).suffix.lower()
    with tempfile.TemporaryDirectory(prefix="pixfabrica-font-upload-") as tmp:
        root = Path(tmp)
        if suffix == ".zip":
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    for name in archive.namelist():
                        if not _is_safe_zip_name(name):
                            raise ValueError(f"unsafe zip entry: {name}")
                    for name in archive.namelist():
                        if name.endswith("/"):
                            continue
                        member_suffix = PurePosixPath(name).suffix.lower()
                        if member_suffix not in _SOURCE_SUFFIXES:
                            continue
                        dest = root / PurePosixPath(name).name
                        dest.write_bytes(archive.read(name))
            except zipfile.BadZipFile as exc:
                raise ValueError("file is not a valid zip archive") from exc
        elif suffix in _SOURCE_SUFFIXES:
            dest = root / sanitize_upload_basename(filename)
            dest.write_bytes(data)
        else:
            raise ValueError("expected .ttf, .otf, or .zip upload")

        sources = sorted(
            path
            for path in root.iterdir()
            if path.is_file() and path.suffix.lower() in _SOURCE_SUFFIXES
        )
        if not sources:
            raise ValueError("upload contains no .ttf or .otf files")
        # Copy out of temp dir before it is removed.
        staging = Path(tempfile.mkdtemp(prefix="pixfabrica-font-stage-"))
        staged: list[Path] = []
        for path in sources:
            target = staging / path.name
            shutil.copy2(path, target)
            staged.append(target)
        return staged


def install_font_sources(
    source_paths: list[Path],
    *,
    target_dir: Path | None = None,
) -> FontInstallResult:
    """Copy upright font sources to the user fonts dir and build woff2 previews."""
    result = FontInstallResult()
    if not source_paths:
        result.warnings.append("no font files provided")
        return result

    dest_root = (target_dir or user_fonts_dir()).resolve()
    dest_root.mkdir(parents=True, exist_ok=True)
    manifest_ids = _manifest_family_ids()
    seen_families: set[str] = set()

    for source in source_paths:
        if not source.is_file():
            result.warnings.append(f"skipped missing file: {source.name}")
            continue
        if not is_allowed_font_path(source):
            result.warnings.append(f"skipped unsupported file: {source.name}")
            continue

        meta = read_font_metadata(source)
        if meta is None:
            result.warnings.append(f"skipped unreadable or italic font: {source.name}")
            continue

        family_name, _weight, _ = meta
        slug = _slugify(family_name)
        if slug in manifest_ids:
            result.warnings.append(
                f"skipped {source.name}: family id {slug!r} is reserved by bundled manifest"
            )
            continue

        dest_name = sanitize_upload_basename(source.name)
        dest_path = dest_root / dest_name
        shutil.copy2(source, dest_path)

        woff2_name = Path(woff2_path_for_source(dest_name)).name
        woff2_path = dest_root / woff2_name
        try:
            _compress_ttf_to_woff2(dest_path, woff2_path)
        except Exception as exc:
            dest_path.unlink(missing_ok=True)
            result.warnings.append(f"failed to build preview for {source.name}: {exc}")
            continue

        result.installed_count += 1
        if family_name not in seen_families:
            seen_families.add(family_name)
            result.families.append(family_name)

    return result


def install_font_upload(data: bytes, filename: str) -> FontInstallResult:
    """Process a web upload (.ttf, .otf, or .zip) into the user fonts directory."""
    try:
        staged = _collect_sources_from_upload(data, filename)
    except ValueError as exc:
        return FontInstallResult(warnings=[str(exc)])
    try:
        return install_font_sources(staged)
    finally:
        staging_dir = staged[0].parent if staged else None
        if staging_dir is not None:
            shutil.rmtree(staging_dir, ignore_errors=True)


def install_fonts_from_directory(source_dir: Path) -> FontInstallResult:
    """Install upright sources found under ``source_dir`` (non-recursive scan)."""
    if not source_dir.is_dir():
        return FontInstallResult()
    sources = sorted(
        path
        for path in source_dir.iterdir()
        if path.is_file() and path.suffix.lower() in _SOURCE_SUFFIXES
    )
    return install_font_sources(sources)
