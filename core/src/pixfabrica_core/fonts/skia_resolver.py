"""Resolve bundled TTF/OTF files to Skia typefaces for the render pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from pixfabrica_core.fonts.catalog import resolve_font_file
from pixfabrica_core.theme.typography import FontPalette, FontSpec

if TYPE_CHECKING:
    import skia

_typeface_cache: dict[tuple[str, int], Any] = {}


def clear_skia_font_cache() -> None:
    _typeface_cache.clear()


def _nearest_weight_entry(
    weights: list[Any],
    weight: int,
) -> Any | None:
    if not weights:
        return None
    return min(weights, key=lambda w: (abs(w.value - weight), w.value))


def resolve_font_source_path(family: str, weight: int) -> Path | None:
    """Map a CSS-like family + weight to a bundled/extra font file, if known."""
    from pixfabrica_core.fonts import get_font_catalog

    catalog = get_font_catalog()
    entry = next((f for f in catalog if f.family == family), None)
    if entry is None:
        return None
    match = _nearest_weight_entry(entry.weights, weight)
    if match is None or not match.source:
        return None
    return resolve_font_file(match.source)


def resolve_skia_typeface(family: str, weight: int) -> skia.Typeface:
    """Load a typeface from bundled assets, falling back to system font matching."""
    import skia

    key = (family, weight)
    cached = _typeface_cache.get(key)
    if cached is not None:
        return cached

    path = resolve_font_source_path(family, weight)
    if path is not None:
        typeface = skia.Typeface.MakeFromFile(str(path))
        if typeface is not None:
            _typeface_cache[key] = typeface
            return typeface

    typeface = skia.Typeface(
        family,
        skia.FontStyle(
            weight,
            skia.FontStyle.kNormal_Width,
            skia.FontStyle.kUpright_Slant,
        ),
    )
    _typeface_cache[key] = typeface
    return typeface


def make_skia_font(spec: FontSpec, *, subpixel: bool = True) -> skia.Font:
    """Build a Skia font for a resolved job typography spec."""
    import skia

    typeface = resolve_skia_typeface(spec.family, spec.weight)
    font = skia.Font(typeface, spec.size)
    if subpixel:
        font.setSubpixel(True)
    return font


def warmup_typography_palette(palette: FontPalette) -> None:
    """Pre-load typefaces referenced by a job palette (optional render optimization)."""
    for role in FontPalette.model_fields:
        spec = getattr(palette, role)
        resolve_skia_typeface(spec.family, spec.weight)
