from __future__ import annotations

import json
from pathlib import Path

import pytest

from pixfabrica_api.compose_tools import compose_tool_definitions, execute_compose_tool

_REPO = Path(__file__).resolve().parents[2]
_HELLO = _REPO / "cli" / "examples" / "hello_world.json"


def test_compose_tool_definitions_include_expected_tools() -> None:
    names = {tool["function"]["name"] for tool in compose_tool_definitions()}
    assert names == {
        "list_catalog_clips",
        "get_clip_detail",
        "build_graph",
        "load_builtin_example",
        "list_typography_roles",
        "list_theme_presets",
        "apply_job_theme",
        "validate_graph",
    }


def test_load_builtin_example_hello_world() -> None:
    result = execute_compose_tool("load_builtin_example", {"name": "hello_world"})
    assert result["ok"] is True
    expected = json.loads(_HELLO.read_text(encoding="utf-8"))
    assert result["graph"] == expected


def test_validate_graph_tool() -> None:
    graph = json.loads(_HELLO.read_text(encoding="utf-8"))
    result = execute_compose_tool("validate_graph", {"graph": graph})
    assert result["ok"] is True


def test_list_typography_roles_tool() -> None:
    result = execute_compose_tool("list_typography_roles", {})
    assert result["ok"] is True
    assert result["defaults"]["hero"] == "display_large"


def test_list_theme_presets_tool() -> None:
    result = execute_compose_tool("list_theme_presets", {})
    assert result["ok"] is True
    assert result["count"] == 16


def test_get_clip_detail() -> None:
    result = execute_compose_tool("get_clip_detail", {"clip_type": "std-static-text"})
    assert result["ok"] is True
    assert result["clip_type"] == "std-static-text"


def test_unknown_tool_raises() -> None:
    with pytest.raises(ValueError, match="unknown compose tool"):
        execute_compose_tool("nope", {})
