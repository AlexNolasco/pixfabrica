"""Tests for UI section title extraction in gen-nls."""

from __future__ import annotations

import json

from pixfabrica_cli.commands.gen_nls import _extract_ui_section_strings


def test_extract_ui_section_strings_preserves_existing_and_defaults(tmp_path) -> None:
    package_dir = tmp_path / "pkg"
    package_dir.mkdir()
    ui = {
        "std-track-card": {
            "sections": [
                {
                    "id": "cover",
                    "title_key": "ui.clip.std-track-card.section.cover",
                    "fields": ["source"],
                },
                {
                    "id": "parameters",
                    "title_key": "ui.clip.std-track-card.section.parameters",
                    "fields": ["title"],
                },
                {
                    "id": "timing",
                    "title_key": "ui.section.timing",
                    "fields": ["start"],
                },
            ]
        }
    }
    (package_dir / "schema.ui.generated.json").write_text(json.dumps(ui), encoding="utf-8")

    strings: dict[str, str] = {}
    existing_en = {"ui.clip.std-track-card.section.cover": "Cover Art"}
    _extract_ui_section_strings(package_dir, strings, existing_en)

    assert strings["ui.clip.std-track-card.section.cover"] == "Cover Art"
    assert strings["ui.clip.std-track-card.section.parameters"] == "Parameters"
    assert strings["ui.section.timing"] == "Timing"


def test_extract_ui_section_strings_skips_when_ui_missing(tmp_path) -> None:
    strings: dict[str, str] = {"plugin.display_name": "Std"}
    _extract_ui_section_strings(tmp_path, strings, {})
    assert strings == {"plugin.display_name": "Std"}
