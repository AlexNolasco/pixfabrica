"""Ensure NC shader headers match clip_license ClassVars."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_STD_ROOT = Path(__file__).resolve().parents[1] / "src" / "pixfabrica_std"
_NC_HEADER = re.compile(r"CC\s+BY-NC(?:-SA)?(?:\s+\d+\.\d+)?", re.IGNORECASE)
_SPDX_FROM_HEADER = {
    "CC BY-NC-SA 3.0": "CC-BY-NC-SA-3.0",
    "CC BY-NC-SA 4.0": "CC-BY-NC-SA-4.0",
    "CC BY-NC-SA": "CC-BY-NC-SA-3.0",
}


def _scan_gl_modules() -> list[Path]:
    paths: list[Path] = []
    for folder in ("background", "effects", "particles"):
        root = _STD_ROOT / folder
        if root.is_dir():
            paths.extend(sorted(root.glob("*_gl.py")))
    return paths


def _normalize_spdx(match: re.Match[str]) -> str:
    if "4.0" in match.group(0):
        return "CC-BY-NC-SA-4.0"
    return "CC-BY-NC-SA-3.0"


def _class_clip_license(path: Path, class_name: str) -> str | None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for stmt in node.body:
                if not isinstance(stmt, ast.AnnAssign):
                    continue
                if (
                    isinstance(stmt.target, ast.Name)
                    and stmt.target.id == "clip_license"
                    and isinstance(stmt.value, ast.Constant)
                    and isinstance(stmt.value.value, str)
                ):
                    return stmt.value.value
    return None


def _gl_classes(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node.name
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name.endswith("GL")
    ]


@pytest.mark.parametrize("path", _scan_gl_modules(), ids=lambda p: p.name)
def test_nc_shader_header_has_matching_clip_license(path: Path):
    text = path.read_text(encoding="utf-8")
    header_match = _NC_HEADER.search(text)
    if header_match is None:
        return
    expected = _normalize_spdx(header_match)
    for class_name in _gl_classes(path):
        license_value = _class_clip_license(path, class_name)
        if license_value is None:
            pytest.fail(f"{path.name}:{class_name} references NC in header but has no clip_license")
        assert license_value == expected
