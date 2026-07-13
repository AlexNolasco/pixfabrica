"""Font install pipeline tests."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
from font_fixtures import write_minimal_font

from pixfabrica_core.fonts import (
    install_font_upload,
    rebuild_font_catalog,
    resolve_font_file,
)


@pytest.fixture
def fonts_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    bundled = tmp_path / "bundled"
    user = tmp_path / "user-fonts"
    bundled.mkdir()
    user.mkdir()
    write_minimal_font(bundled / "Fixture-Regular.ttf", family_name="Fixture Sans", weight=400)
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
    (bundled / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setenv("PIXFABRICA_BUNDLED_FONTS_DIR", str(bundled))
    monkeypatch.setenv("PIXFABRICA_USER_FONTS_DIR", str(user))
    monkeypatch.delenv("PIXFABRICA_FONTS_DIR", raising=False)
    rebuild_font_catalog()
    return bundled, user


def test_install_single_ttf(fonts_env: tuple[Path, Path], tmp_path: Path) -> None:
    _bundled, user = fonts_env
    ttf = tmp_path / "Custom-Regular.ttf"
    write_minimal_font(ttf, family_name="Custom Family", weight=400)
    data = ttf.read_bytes()

    result = install_font_upload(data, "Custom-Regular.ttf")
    assert result.ok
    assert result.installed_count == 1
    assert result.families == ["Custom Family"]
    assert (user / "Custom-Regular.ttf").is_file()
    assert (user / "Custom-Regular.woff2").is_file()

    catalog = rebuild_font_catalog()
    ids = {entry.id for entry in catalog}
    assert "custom-family" in ids


def test_install_rejects_manifest_collision(fonts_env: tuple[Path, Path]) -> None:
    _bundled, user = fonts_env
    ttf = user / "Fixture-Regular.ttf"
    write_minimal_font(ttf, family_name="Fixture Sans", weight=400)
    result = install_font_upload(ttf.read_bytes(), "Fixture-Regular.ttf")
    assert not result.ok
    assert any("manifest" in warning for warning in result.warnings)


def test_install_zip_best_effort(fonts_env: tuple[Path, Path], tmp_path: Path) -> None:
    _bundled, user = fonts_env
    good = tmp_path / "Good-Regular.ttf"
    write_minimal_font(good, family_name="Good Family", weight=400)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("Good-Regular.ttf", good.read_bytes())
        archive.writestr("notes.txt", b"ignore me")

    result = install_font_upload(buffer.getvalue(), "fonts.zip")
    assert result.ok
    assert result.installed_count == 1
    assert resolve_font_file("Good-Regular.woff2", user_dir=user) is not None


def test_install_zip_fails_when_empty(fonts_env: tuple[Path, Path]) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("notes.txt", b"no fonts here")
    result = install_font_upload(buffer.getvalue(), "empty.zip")
    assert not result.ok
