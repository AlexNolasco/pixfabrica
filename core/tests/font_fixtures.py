"""Minimal TTF fixtures for font catalog tests."""

from __future__ import annotations

from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen


def _empty_glyph(advance: int = 500):
    pen = TTGlyphPen(None)
    pen.moveTo((0, 0))
    pen.lineTo((advance, 0))
    pen.lineTo((advance, 1))
    pen.lineTo((0, 1))
    pen.closePath()
    return pen.glyph()


def _letter_a_glyph():
    pen = TTGlyphPen(None)
    pen.moveTo((50, 0))
    pen.lineTo((550, 0))
    pen.lineTo((300, 700))
    pen.closePath()
    return pen.glyph()


def write_minimal_font(
    path: Path,
    *,
    family_name: str = "Fixture Sans",
    style_name: str = "Regular",
    weight: int = 400,
) -> None:
    """Write a tiny valid upright TTF (for manifest / woff2 build tests)."""
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder([".notdef", ".null", "space", "A"])
    fb.setupCharacterMap({32: "space", 65: "A"})
    fb.setupGlyf(
        {
            ".notdef": _empty_glyph(500),
            ".null": _empty_glyph(0),
            "space": _empty_glyph(250),
            "A": _letter_a_glyph(),
        }
    )
    fb.setupHorizontalMetrics(
        {
            ".notdef": (500, 0),
            ".null": (0, 0),
            "space": (250, 0),
            "A": (600, 0),
        }
    )
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupHead(unitsPerEm=1000)
    fb.setupNameTable(
        {
            "familyName": family_name,
            "styleName": style_name,
            "uniqueFontIdentifier": f"{family_name} {style_name}",
            "fullName": f"{family_name} {style_name}",
            "psName": family_name.replace(" ", "") + "-" + style_name.replace(" ", ""),
        }
    )
    fb.setupOS2(usWeightClass=weight, fsSelection=0)
    fb.setupPost()
    path.parent.mkdir(parents=True, exist_ok=True)
    fb.save(path)
