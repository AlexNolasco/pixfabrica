from __future__ import annotations

import json
from pathlib import Path

from pixfabrica_api.compose_theme import (
    apply_job_theme_to_graph,
    list_theme_presets_for_compose,
    normalize_editor_job_context,
)

_REPO = Path(__file__).resolve().parents[2]
_HELLO = json.loads((_REPO / "cli" / "examples" / "hello_world.json").read_text(encoding="utf-8"))

_ROSE_DARK = {
    "colors": {
        "primary": "#f48fb1",
        "secondary": "#f06292",
        "tertiary": "#c2185b",
        "accent": "#ff80ab",
        "background": "#1a0a10",
        "neutral": "#fce4ec",
        "neutral_variant": "#8d4a62",
    },
    "palette_source": {"type": "named", "theme": "rose", "variant": "dark"},
}


def test_list_theme_presets_for_compose() -> None:
    result = list_theme_presets_for_compose()
    assert result["ok"] is True
    assert result["count"] == 16
    assert result["presets"][0]["label"]


def test_normalize_editor_job_context() -> None:
    ctx = normalize_editor_job_context(_ROSE_DARK)
    assert ctx is not None
    assert ctx["palette_source"]["theme"] == "rose"


def test_apply_job_theme_named_preset() -> None:
    result = apply_job_theme_to_graph(
        _HELLO, {"theme": "midnight", "variant": "dark"}, editor_job_context=None
    )
    assert result["ok"] is True
    graph = result["graph"]
    assert graph["palette_source"] == {"type": "named", "theme": "midnight", "variant": "dark"}
    assert graph["colors"]["background"] == "#050a0e"


def test_apply_job_theme_use_editor_context() -> None:
    result = apply_job_theme_to_graph(
        _HELLO,
        {"use_editor_theme": True},
        editor_job_context=normalize_editor_job_context(_ROSE_DARK),
    )
    assert result["ok"] is True
    graph = result["graph"]
    assert graph["palette_source"]["theme"] == "rose"
    assert graph["colors"]["accent"] == "#ff80ab"


def test_apply_job_theme_color_patch() -> None:
    base = apply_job_theme_to_graph(
        _HELLO,
        {"theme": "violet", "variant": "dark"},
        editor_job_context=None,
    )
    assert base["ok"] is True
    result = apply_job_theme_to_graph(
        base["graph"],
        {"colors": {"accent": "#00ffcc"}},
        editor_job_context=None,
    )
    assert result["ok"] is True
    graph = result["graph"]
    assert graph["colors"]["accent"] == "#00ffcc"
    assert graph["palette_source"] == {"type": "custom"}


def test_apply_job_theme_missing_args() -> None:
    result = apply_job_theme_to_graph(_HELLO, {}, editor_job_context=None)
    assert result["ok"] is False
