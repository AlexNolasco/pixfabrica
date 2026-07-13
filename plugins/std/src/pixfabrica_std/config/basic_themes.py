"""BasicThemes — baked named palettes with optional image-based palette extraction."""

from __future__ import annotations

import asyncio
import colorsys
import hashlib
import io
import urllib.request
from pathlib import Path
from typing import ClassVar

from pydantic import Field

from pixfabrica_core.clips import ClipCategory
from pixfabrica_core.composition.config import ThemeContext, ThemeSetting
from pixfabrica_core.theme.color import Color, ColorPalette
from pixfabrica_core.theme.presets import (
    ThemeName,
    ThemeVariant,
    get_named_palette,
)


def _luminance(r: int, g: int, b: int) -> float:
    return 0.2126 * r / 255 + 0.7152 * g / 255 + 0.0722 * b / 255


def _saturation(r: int, g: int, b: int) -> float:
    _, s, _ = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    return s


def _to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}"


def _derive_accent(r: int, g: int, b: int) -> Color:
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    if s > 0.15:
        h = (h + 30 / 360) % 1.0
    else:
        v = min(1.0, v + 0.15)
    nr, ng, nb = colorsys.hsv_to_rgb(h, s, v)
    return Color(_to_hex(round(nr * 255), round(ng * 255), round(nb * 255)))


def _palette_from_image_bytes(data: bytes) -> ColorPalette:
    try:
        from colorthief import ColorThief
    except ImportError as exc:
        raise ImportError(
            "colorthief is required for image palette extraction: pip install colorthief"
        ) from exc

    ct = ColorThief(io.BytesIO(data))
    colors = ct.get_palette(color_count=6, quality=5)

    if len(colors) < 6:
        raise ValueError(
            f"BasicThemes: image too uniform, only {len(colors)} dominant colors extracted"
        )

    by_lum = sorted(colors, key=lambda c: _luminance(*c))
    background = by_lum[0]
    neutral_variant_rgb = by_lum[4]
    neutral = by_lum[5]

    by_sat = sorted(by_lum[1:4], key=lambda c: _saturation(*c), reverse=True)
    primary, secondary, tertiary = by_sat[0], by_sat[1], by_sat[2]

    return ColorPalette(
        primary=Color(_to_hex(*primary)),
        secondary=Color(_to_hex(*secondary)),
        tertiary=Color(_to_hex(*tertiary)),
        accent=_derive_accent(*primary),
        background=Color(_to_hex(*background)),
        neutral=Color(_to_hex(*neutral)),
        neutral_variant=Color(_to_hex(*neutral_variant_rgb)),
    )


def _download_url(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310
        return resp.read()


def palette_from_image_bytes(data: bytes) -> ColorPalette:
    """Extract a ColorPalette from raw image bytes (ColorThief)."""
    return _palette_from_image_bytes(data)


async def palette_from_source(source: str, cache_dir: Path | None = None) -> ColorPalette:
    """Load image bytes from a URL or local path and extract a palette."""
    if source.startswith(("http://", "https://")):
        cache = cache_dir or Path.cwd() / ".cache" / "theme"
        url_hash = hashlib.sha256(source.encode()).hexdigest()[:16]
        cached = cache / f"theme_{url_hash}"
        if cached.exists():
            return _palette_from_image_bytes(cached.read_bytes())
        cache.mkdir(parents=True, exist_ok=True)
        data = await asyncio.to_thread(_download_url, source)
        cached.write_bytes(data)
        return _palette_from_image_bytes(data)
    path = Path(source)
    if not path.is_file():
        raise FileNotFoundError(f"theme source file not found: {path}")
    return _palette_from_image_bytes(path.read_bytes())


class BasicThemes(ThemeSetting):
    """Curated named color palettes with optional image-based extraction.

    When ``source`` is set the named theme is ignored and the palette is derived
    from the image (file path or URL).  On failure the job is aborted — no silent
    fallback.
    """

    setting_type: ClassVar[str] = "std-basic-themes"
    clip_category: ClassVar[ClipCategory] = ClipCategory.THEME_GENERATOR

    theme: ThemeName = Field(
        default="amber",
        description="Named palette used when no source image is provided.",
    )
    variant: ThemeVariant = Field(
        default="dark",
        description="Dark or light version of the named palette.",
    )
    source: str | None = Field(
        default=None,
        description=(
            "Image file path or URL. When set the palette is extracted from the image "
            "and the named theme/variant are ignored."
        ),
    )

    async def resolve(self, ctx: ThemeContext) -> ColorPalette:
        if self.source:
            image_bytes = await self._fetch_source(ctx)
            return _palette_from_image_bytes(image_bytes)
        return get_named_palette(self.theme, self.variant)

    async def _fetch_source(self, ctx: ThemeContext) -> bytes:
        assert self.source is not None
        if self.source.startswith(("http://", "https://")):
            url_hash = hashlib.sha256(self.source.encode()).hexdigest()[:16]
            cached = ctx.cache_dir / f"theme_{url_hash}"
            if cached.exists():
                return cached.read_bytes()
            ctx.cache_dir.mkdir(parents=True, exist_ok=True)
            data = await asyncio.to_thread(_download_url, self.source)
            cached.write_bytes(data)
            return data
        path = Path(self.source)
        if not path.exists():
            raise FileNotFoundError(f"BasicThemes: source file not found: {path}")
        return path.read_bytes()
