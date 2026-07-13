"""Named job color presets (shared by web API and theme plugins)."""

from __future__ import annotations

from typing import Literal

from pixfabrica_core.theme.color import Color, ColorPalette

ThemeName = Literal["amber", "violet", "rose", "emerald", "slate", "sky", "gold", "midnight"]
ThemeVariant = Literal["dark", "light"]

THEME_ORDER: list[ThemeName] = [
    "amber",
    "violet",
    "rose",
    "emerald",
    "slate",
    "sky",
    "gold",
    "midnight",
]

NAMED_PALETTES: dict[tuple[str, str], ColorPalette] = {
    # amber — warm golden on dark brown
    ("amber", "dark"): ColorPalette(
        primary=Color("#f1c371"),
        secondary=Color("#f8efaf"),
        tertiary=Color("#c99023"),
        accent=Color("#ff9f43"),
        background=Color("#231b10"),
        neutral=Color("#e1dcc5"),
        neutral_variant=Color("#8b6b40"),
    ),
    ("amber", "light"): ColorPalette(
        primary=Color("#b87a10"),
        secondary=Color("#d4a520"),
        tertiary=Color("#7a4e05"),
        accent=Color("#e05c10"),
        background=Color("#faf5eb"),
        neutral=Color("#1a1208"),
        neutral_variant=Color("#6b4820"),
    ),
    # violet — purple/indigo
    ("violet", "dark"): ColorPalette(
        primary=Color("#b39ddb"),
        secondary=Color("#9575cd"),
        tertiary=Color("#7e57c2"),
        accent=Color("#ea80fc"),
        background=Color("#1a1228"),
        neutral=Color("#ede7f6"),
        neutral_variant=Color("#5e35b1"),
    ),
    ("violet", "light"): ColorPalette(
        primary=Color("#7e57c2"),
        secondary=Color("#5e35b1"),
        tertiary=Color("#4527a0"),
        accent=Color("#d500f9"),
        background=Color("#f3e5f5"),
        neutral=Color("#1a0533"),
        neutral_variant=Color("#9c27b0"),
    ),
    # rose — pink/red
    ("rose", "dark"): ColorPalette(
        primary=Color("#f48fb1"),
        secondary=Color("#f06292"),
        tertiary=Color("#c2185b"),
        accent=Color("#ff4081"),
        background=Color("#1a0d10"),
        neutral=Color("#fce4ec"),
        neutral_variant=Color("#880e4f"),
    ),
    ("rose", "light"): ColorPalette(
        primary=Color("#e91e63"),
        secondary=Color("#f06292"),
        tertiary=Color("#ad1457"),
        accent=Color("#f50057"),
        background=Color("#fff0f5"),
        neutral=Color("#1a0010"),
        neutral_variant=Color("#6d2040"),
    ),
    # emerald — green/teal
    ("emerald", "dark"): ColorPalette(
        primary=Color("#80cbc4"),
        secondary=Color("#4db6ac"),
        tertiary=Color("#26a69a"),
        accent=Color("#64ffda"),
        background=Color("#0d1f1e"),
        neutral=Color("#e0f2f1"),
        neutral_variant=Color("#00796b"),
    ),
    ("emerald", "light"): ColorPalette(
        primary=Color("#2e7d32"),
        secondary=Color("#388e3c"),
        tertiary=Color("#1b5e20"),
        accent=Color("#00c853"),
        background=Color("#f1f8e9"),
        neutral=Color("#1b2016"),
        neutral_variant=Color("#558b2f"),
    ),
    # slate — cool blue-gray
    ("slate", "dark"): ColorPalette(
        primary=Color("#90a4ae"),
        secondary=Color("#78909c"),
        tertiary=Color("#546e7a"),
        accent=Color("#84ffff"),
        background=Color("#0f1923"),
        neutral=Color("#eceff1"),
        neutral_variant=Color("#455a64"),
    ),
    ("slate", "light"): ColorPalette(
        primary=Color("#455a64"),
        secondary=Color("#607d8b"),
        tertiary=Color("#263238"),
        accent=Color("#0097a7"),
        background=Color("#eceff1"),
        neutral=Color("#102027"),
        neutral_variant=Color("#78909c"),
    ),
    # sky — light blue/cyan on dark navy
    ("sky", "dark"): ColorPalette(
        primary=Color("#81d4fa"),
        secondary=Color("#29b6f6"),
        tertiary=Color("#01579b"),
        accent=Color("#00e5ff"),
        background=Color("#0a1929"),
        neutral=Color("#e1f5fe"),
        neutral_variant=Color("#0288d1"),
    ),
    ("sky", "light"): ColorPalette(
        primary=Color("#0288d1"),
        secondary=Color("#039be5"),
        tertiary=Color("#01579b"),
        accent=Color("#00b0ff"),
        background=Color("#e1f5fe"),
        neutral=Color("#0a1929"),
        neutral_variant=Color("#4fc3f7"),
    ),
    # gold — champagne/warm gold on dark navy
    ("gold", "dark"): ColorPalette(
        primary=Color("#e8c597"),
        secondary=Color("#cd9b47"),
        tertiary=Color("#8c6520"),
        accent=Color("#ffe0a3"),
        background=Color("#121c21"),
        neutral=Color("#f0e6d3"),
        neutral_variant=Color("#4e7d95"),
    ),
    ("gold", "light"): ColorPalette(
        primary=Color("#8c6520"),
        secondary=Color("#a07828"),
        tertiary=Color("#5a3f0a"),
        accent=Color("#cd9b47"),
        background=Color("#fdf8f0"),
        neutral=Color("#1a1000"),
        neutral_variant=Color("#c9a555"),
    ),
    # midnight — near-monochrome, deep dark
    ("midnight", "dark"): ColorPalette(
        primary=Color("#b0bec5"),
        secondary=Color("#78909c"),
        tertiary=Color("#546e7a"),
        accent=Color("#90caf9"),
        background=Color("#050a0e"),
        neutral=Color("#eceff1"),
        neutral_variant=Color("#37474f"),
    ),
    ("midnight", "light"): ColorPalette(
        primary=Color("#455a64"),
        secondary=Color("#607d8b"),
        tertiary=Color("#263238"),
        accent=Color("#1565c0"),
        background=Color("#fafafa"),
        neutral=Color("#1c1c1c"),
        neutral_variant=Color("#9e9e9e"),
    ),
}


def palette_to_hex_dict(palette: ColorPalette) -> dict[str, str]:
    return palette.model_dump(mode="json")


def get_named_palette(theme: ThemeName, variant: ThemeVariant) -> ColorPalette:
    return NAMED_PALETTES[(theme, variant)]


def preset_label(theme: ThemeName, variant: ThemeVariant) -> str:
    return f"{theme.title()} ({variant.title()})"


def list_theme_presets() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for theme in THEME_ORDER:
        for variant in ("dark", "light"):
            palette = get_named_palette(theme, variant)
            rows.append(
                {
                    "theme": theme,
                    "variant": variant,
                    "label": preset_label(theme, variant),
                    "colors": palette_to_hex_dict(palette),
                }
            )
    return rows
