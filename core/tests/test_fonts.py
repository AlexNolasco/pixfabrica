"""Font manifest, catalog, build, and file resolution tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from font_fixtures import write_minimal_font

from pixfabrica_core.fonts import (
    build_font_catalog,
    rebuild_font_catalog,
    resolve_font_file,
    run_font_build,
)
from pixfabrica_core.fonts.manifest import FontManifestError, load_manifest


@pytest.fixture
def fonts_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "fonts"
    root.mkdir()
    monkeypatch.setenv("PIXFABRICA_BUNDLED_FONTS_DIR", str(root))
    monkeypatch.delenv("PIXFABRICA_FONTS_DIR", raising=False)
    return root


def _write_manifest(fonts_dir: Path, *, family_id: str = "fixture-sans") -> None:
    write_minimal_font(fonts_dir / "Fixture-Regular.ttf", family_name="Fixture Sans", weight=400)
    manifest = {
        "version": 1,
        "families": [
            {
                "id": family_id,
                "family": "Fixture Sans",
                "label": "Fixture Sans",
                "category": "sans",
                "weights": [{"value": 400, "source": "Fixture-Regular.ttf"}],
            }
        ],
    }
    (fonts_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_load_manifest_and_catalog(fonts_dir: Path) -> None:
    _write_manifest(fonts_dir)
    catalog = rebuild_font_catalog()
    assert len(catalog) == 1
    assert catalog[0].id == "fixture-sans"
    assert catalog[0].weights[0].preview_url == "/fonts/files/Fixture-Regular.woff2"


def test_font_build_creates_woff2(fonts_dir: Path) -> None:
    _write_manifest(fonts_dir)
    result = run_font_build(fonts_dir=fonts_dir)
    assert result.ok
    assert (fonts_dir / "Fixture-Regular.woff2").is_file()
    assert "Fixture-Regular.woff2" in result.created


def test_font_build_check_dry_run(fonts_dir: Path) -> None:
    _write_manifest(fonts_dir)
    drift = run_font_build(fonts_dir=fonts_dir, dry_run=True)
    assert not drift.ok
    assert any("preview file" in err for err in drift.errors)

    run_font_build(fonts_dir=fonts_dir)
    ok = run_font_build(fonts_dir=fonts_dir, dry_run=True)
    assert ok.ok


def test_check_passes_with_woff2_only(fonts_dir: Path) -> None:
    """Check does not require .ttf when .woff2 preview is already present."""
    _write_manifest(fonts_dir)
    run_font_build(fonts_dir=fonts_dir)
    (fonts_dir / "Fixture-Regular.ttf").unlink()

    ok = run_font_build(fonts_dir=fonts_dir, dry_run=True)
    assert ok.ok


def test_resolve_font_file_bundled(fonts_dir: Path) -> None:
    _write_manifest(fonts_dir)
    run_font_build(fonts_dir=fonts_dir)
    path = resolve_font_file("Fixture-Regular.woff2", bundled_dir=fonts_dir)
    assert path is not None
    assert path.name == "Fixture-Regular.woff2"


def test_resolve_rejects_traversal(fonts_dir: Path) -> None:
    _write_manifest(fonts_dir)
    assert resolve_font_file("../secret.ttf", bundled_dir=fonts_dir) is None


def test_scan_extra_dir(fonts_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_manifest(fonts_dir)
    extra = tmp_path / "extra"
    extra.mkdir()
    write_minimal_font(extra / "Extra-Regular.ttf", family_name="Extra Family", weight=500)
    monkeypatch.setenv("PIXFABRICA_FONTS_DIR", str(extra))

    catalog = build_font_catalog(bundled_dir=fonts_dir, extra_dir=extra)
    ids = {f.id for f in catalog}
    assert "fixture-sans" in ids
    assert "extra-family" in ids


def test_duplicate_manifest_id_raises(fonts_dir: Path) -> None:
    weight = {"value": 400, "source": "Fixture-Regular.ttf"}
    (fonts_dir / "manifest.json").write_text(
        json.dumps(
            {
                "version": 1,
                "families": [
                    {"id": "dup", "family": "A", "category": "sans", "weights": [weight]},
                    {"id": "dup", "family": "B", "category": "sans", "weights": [weight]},
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(FontManifestError):
        load_manifest(fonts_dir / "manifest.json")
