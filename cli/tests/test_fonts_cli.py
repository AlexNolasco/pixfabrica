"""CLI font build / check / list commands."""

from __future__ import annotations

import json
from pathlib import Path

from font_fixtures import write_minimal_font
from typer.testing import CliRunner

from pixfabrica_cli.main import app

runner = CliRunner()


def _setup_fonts_dir(path: Path) -> None:
    write_minimal_font(path / "Fixture-Regular.ttf", family_name="Fixture Sans", weight=400)
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
    (path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_fonts_build_and_check(tmp_path: Path) -> None:
    fonts_dir = tmp_path / "fonts"
    fonts_dir.mkdir()
    _setup_fonts_dir(fonts_dir)

    fail = runner.invoke(app, ["fonts", "check", "--fonts-dir", str(fonts_dir)])
    assert fail.exit_code != 0

    ok = runner.invoke(app, ["fonts", "build", "--fonts-dir", str(fonts_dir)])
    assert ok.exit_code == 0, ok.stdout
    assert (fonts_dir / "Fixture-Regular.woff2").is_file()

    check = runner.invoke(app, ["fonts", "check", "--fonts-dir", str(fonts_dir)])
    assert check.exit_code == 0, check.stdout


def test_fonts_list_json(tmp_path: Path) -> None:
    fonts_dir = tmp_path / "fonts"
    fonts_dir.mkdir()
    _setup_fonts_dir(fonts_dir)
    runner.invoke(app, ["fonts", "build", "--fonts-dir", str(fonts_dir)])

    result = runner.invoke(app, ["fonts", "list", "--fonts-dir", str(fonts_dir), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data[0]["id"] == "fixture-sans"
