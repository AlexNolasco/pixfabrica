"""Scan optional extra font directory (runtime + build metadata)."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from pixfabrica_core.fonts.models import FontCategory, FontFamilyEntry, FontWeightEntry
from pixfabrica_core.fonts.paths import is_allowed_font_path, woff2_path_for_source

log = logging.getLogger("pixfabrica_core.fonts.scan")

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(name: str) -> str:
    slug = _slugify_raw(name)
    return slug or "font"


def _slugify_raw(name: str) -> str:
    return _SLUG_RE.sub("-", name.lower()).strip("-")


def read_font_metadata(path: Path) -> tuple[str, int, bool] | None:
    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        log.warning("fontTools not installed; cannot scan extra fonts dir")
        return None

    try:
        font = TTFont(path, lazy=True)
        family = font["name"].getBestFamilyName()
        if not family:
            return None
        os2 = font["OS/2"]
        weight = int(getattr(os2, "usWeightClass", 400))
        weight = max(100, min(900, weight))
        italic = bool(getattr(os2, "fsSelection", 0) & 0x1)  # ITALIC
        font.close()
        if italic:
            return None
        return family, weight, False
    except Exception as exc:
        log.debug("skip font file %s: %s", path, exc)
        return None


def _guess_category(family_name: str, path: Path) -> FontCategory:
    lower = f"{family_name} {path.stem}".lower()
    if "mono" in lower or "code" in lower:
        return "mono"
    return "sans"


def scan_extra_fonts_dir(
    extra_dir: Path,
    *,
    manifest_ids: frozenset[str],
    preview_url_prefix: str = "/fonts/files",
) -> list[FontFamilyEntry]:
    """Register upright faces from *extra_dir* not already in the manifest (by id)."""
    if not extra_dir.is_dir():
        return []

    # family slug -> { weight -> (path, woff2 name) }
    grouped: dict[str, dict[int, tuple[str, str, str, FontCategory]]] = {}

    for path in sorted(extra_dir.rglob("*")):
        if not path.is_file():
            continue
        if not is_allowed_font_path(path):
            continue
        if path.suffix.lower() in {".woff", ".woff2"}:
            continue
        try:
            path.resolve().relative_to(extra_dir.resolve())
        except ValueError:
            continue

        meta = read_font_metadata(path)
        if meta is None:
            continue
        family_name, weight, _ = meta
        slug = _slugify(family_name)
        if slug in manifest_ids:
            continue

        rel_name = path.name
        woff2_name = Path(woff2_path_for_source(rel_name)).name
        category = _guess_category(family_name, path)
        grouped.setdefault(slug, {})
        if weight not in grouped[slug]:
            grouped[slug][weight] = (family_name, rel_name, woff2_name, category)

    entries: list[FontFamilyEntry] = []
    for slug, weights_map in sorted(grouped.items()):
        family_name, _, _, category = next(iter(weights_map.values()))
        weight_entries = [
            FontWeightEntry(
                value=weight,
                source=source_name,
                preview_url=f"{preview_url_prefix}/{woff2_name}",
            )
            for weight, (_, source_name, woff2_name, _) in sorted(weights_map.items())
        ]
        entries.append(
            FontFamilyEntry(
                id=slug,
                family=family_name,
                label=family_name,
                category=category,
                weights=weight_entries,
            )
        )
    return entries
