"""Skia font resolver tests (requires skia-python in the test env)."""

from __future__ import annotations

import json

import pytest
from font_fixtures import write_minimal_font

from pixfabrica_core.fonts import (
    clear_skia_font_cache,
    configure_fonts_for_tests,
    make_skia_font,
    rebuild_font_catalog,
    resolve_font_source_path,
)
from pixfabrica_core.theme.typography import FontSpec

pytest.importorskip("skia")


@pytest.fixture
def fonts_dir(tmp_path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "fonts"
    root.mkdir()
    monkeypatch.setenv("PIXFABRICA_BUNDLED_FONTS_DIR", str(root))
    monkeypatch.delenv("PIXFABRICA_FONTS_DIR", raising=False)
    return root


def _write_manifest(fonts_dir) -> None:
    write_minimal_font(fonts_dir / "Fixture-Regular.ttf", family_name="Fixture Sans", weight=400)
    manifest = {
        "version": 1,
        "families": [
            {
                "id": "fixture-sans",
                "family": "Fixture Sans",
                "label": "Fixture Sans",
                "category": "sans",
                "weights": [{"value": 400, "source": "Fixture-Regular.ttf"}],
            }
        ],
    }
    (fonts_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_resolve_font_source_path(fonts_dir) -> None:
    _write_manifest(fonts_dir)
    configure_fonts_for_tests(bundled_dir=fonts_dir)
    rebuild_font_catalog()
    clear_skia_font_cache()

    path = resolve_font_source_path("Fixture Sans", 400)
    assert path is not None
    assert path.name == "Fixture-Regular.ttf"


def test_make_skia_font_loads_bundled_ttf(fonts_dir) -> None:
    _write_manifest(fonts_dir)
    configure_fonts_for_tests(bundled_dir=fonts_dir)
    rebuild_font_catalog()
    clear_skia_font_cache()

    spec = FontSpec(family="Fixture Sans", weight=400, size=24.0)
    font = make_skia_font(spec)
    assert font.getSize() == 24.0
    typeface = font.getTypeface()
    assert typeface is not None
    assert typeface.getFamilyName() == "Fixture Sans"
