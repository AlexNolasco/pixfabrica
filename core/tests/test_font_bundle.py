"""Bundle export/import for custom typography fonts."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
from font_fixtures import write_minimal_font

from pixfabrica_core.catalog import build_catalog_cache
from pixfabrica_core.fonts import install_font_upload, rebuild_font_catalog
from pixfabrica_core.project_bundles.export import export_project_bundle
from pixfabrica_core.project_bundles.fonts import FONTS_ASSET_DIR
from pixfabrica_core.project_bundles.import_bundle import import_project_bundle


@pytest.fixture
def fonts_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    bundled = tmp_path / "bundled"
    user = tmp_path / "user-fonts"
    bundled.mkdir()
    user.mkdir()
    write_minimal_font(bundled / "Fixture-Regular.ttf", family_name="Fixture Sans", weight=400)
    (bundled / "manifest.json").write_text(
        json.dumps(
            {
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
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("PIXFABRICA_BUNDLED_FONTS_DIR", str(bundled))
    monkeypatch.setenv("PIXFABRICA_USER_FONTS_DIR", str(user))
    monkeypatch.delenv("PIXFABRICA_FONTS_DIR", raising=False)
    rebuild_font_catalog()
    return bundled, user


def _project_with_custom_typography() -> dict:
    return {
        "schema_version": 1,
        "title": "Font Bundle",
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "duration": 10,
        "typography": {
            "body_medium": {
                "family": "Custom Family",
                "weight": 400,
                "size": 29,
                "line_height": 1.24,
            },
        },
        "tracks": [],
        "sounds": [],
    }


def test_export_and_import_custom_fonts(
    fonts_env: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _bundled, user = fonts_env
    custom = tmp_path / "Custom-Regular.ttf"
    write_minimal_font(custom, family_name="Custom Family", weight=400)
    install_result = install_font_upload(custom.read_bytes(), "Custom-Regular.ttf")
    assert install_result.ok
    rebuild_font_catalog()

    catalog = build_catalog_cache([])
    payload, _filename = export_project_bundle(
        _project_with_custom_typography(),
        media_root=tmp_path,
        catalog=catalog,
    )

    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = archive.namelist()
        assert f"{FONTS_ASSET_DIR}/Custom-Regular.ttf" in names
        assert f"{FONTS_ASSET_DIR}/Custom-Regular.woff2" in names

    import_user = tmp_path / "import-user-fonts"
    import_user.mkdir()
    import_bundle = tmp_path / "bundle"
    import_bundle.mkdir()
    monkeypatch.setenv("PIXFABRICA_USER_FONTS_DIR", str(import_user))

    imported = import_project_bundle(payload, bundle_dir=import_bundle, catalog=catalog)
    assert imported["typography"]["body_medium"]["family"] == "Custom Family"
    rebuild_font_catalog()
    catalog_after = rebuild_font_catalog()
    assert any(entry.family == "Custom Family" for entry in catalog_after)
    assert (import_user / "Custom-Regular.ttf").is_file()
