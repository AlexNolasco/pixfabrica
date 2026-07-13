"""Validate bundled fonts and generate woff2 previews."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pixfabrica_core.fonts.manifest import FontManifestError, load_manifest
from pixfabrica_core.fonts.paths import (
    default_bundled_fonts_dir,
    default_manifest_path,
    woff2_path_for_source,
)


@dataclass
class FontBuildResult:
    created: list[str] = field(default_factory=list)
    up_to_date: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _compress_ttf_to_woff2(source: Path, dest: Path) -> None:
    from fontTools.ttLib.woff2 import compress

    dest.parent.mkdir(parents=True, exist_ok=True)
    compress(str(source), str(dest))


def _check_weight(
    *,
    source_name: str,
    ttf_path: Path,
    woff2_path: Path,
    woff2_name: str,
    result: FontBuildResult,
) -> None:
    """Check mode: require woff2 previews; sources optional (build regenerates from .ttf)."""
    if not woff2_path.is_file():
        if ttf_path.is_file():
            hint = f"missing preview file: {woff2_name} (run: uv run pixfabrica fonts build)"
        else:
            hint = (
                f"missing preview file: {woff2_name} "
                f"(add {source_name} per assets/fonts/README.md, then run fonts build)"
            )
        result.errors.append(hint)
        return

    if ttf_path.is_file() and ttf_path.stat().st_mtime > woff2_path.stat().st_mtime:
        result.errors.append(f"woff2 out of date: {woff2_name} (run fonts build)")
        return

    result.up_to_date.append(woff2_name)


def run_font_build(
    *,
    fonts_dir: Path | None = None,
    manifest_path: Path | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> FontBuildResult:
    root = (fonts_dir or default_bundled_fonts_dir()).resolve()
    manifest_file = manifest_path or default_manifest_path(root)
    result = FontBuildResult()

    try:
        manifest = load_manifest(manifest_file)
    except FontManifestError as exc:
        result.errors.append(str(exc))
        return result

    for family in manifest.families:
        for weight in family.weights:
            ttf_path = root / weight.source
            woff2_name = Path(woff2_path_for_source(weight.source)).name
            woff2_path = root / woff2_name

            if dry_run:
                _check_weight(
                    source_name=weight.source,
                    ttf_path=ttf_path,
                    woff2_path=woff2_path,
                    woff2_name=woff2_name,
                    result=result,
                )
                continue

            if not ttf_path.is_file():
                result.errors.append(f"missing source file: {weight.source}")
                continue

            needs_build = force or not woff2_path.is_file()
            if woff2_path.is_file() and not force:
                if ttf_path.stat().st_mtime > woff2_path.stat().st_mtime:
                    needs_build = True
                else:
                    result.up_to_date.append(woff2_name)
                    continue

            if needs_build:
                try:
                    _compress_ttf_to_woff2(ttf_path, woff2_path)
                    result.created.append(woff2_name)
                except Exception as exc:
                    result.errors.append(f"failed to build {woff2_name}: {exc}")

    return result
