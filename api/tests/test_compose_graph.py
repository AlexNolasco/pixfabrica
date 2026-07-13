from __future__ import annotations

import json
from pathlib import Path

from pixfabrica_api.compose_graph import validate_graph_for_compose

_REPO = Path(__file__).resolve().parents[2]
_HELLO = _REPO / "cli" / "examples" / "hello_world.json"


def test_validate_graph_accepts_hello_world() -> None:
    graph = json.loads(_HELLO.read_text(encoding="utf-8"))
    result = validate_graph_for_compose(graph)
    assert result["ok"] is True
    assert result["title"] == "Hello, World!"
    assert result["track_count"] == 1


def test_validate_graph_rejects_invalid_payload() -> None:
    result = validate_graph_for_compose({"tracks": "nope"})
    assert result["ok"] is False
    assert result["errors"]
