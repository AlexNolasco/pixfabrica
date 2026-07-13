from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from pixfabrica_api.compose_orchestrator import reset_compose_sessions, run_compose_chat

_REPO = Path(__file__).resolve().parents[2]
_HELLO = json.loads((_REPO / "cli" / "examples" / "hello_world.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _clear_sessions() -> None:
    reset_compose_sessions()


def _tool_call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": "call-1",
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": json.dumps(arguments),
                },
            }
        ],
    }


def test_run_compose_chat_hello_world_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [
        {
            "message": _tool_call("load_builtin_example", {"name": "hello_world"}),
            "prompt_eval_count": 512,
        },
        {
            "message": _tool_call("validate_graph", {"graph": _HELLO}),
            "prompt_eval_count": 900,
        },
        {
            "message": {
                "role": "assistant",
                "content": "Created a hello world composition.",
            },
            "prompt_eval_count": 1100,
        },
    ]

    def fake_chat(**kwargs: Any) -> dict[str, Any]:
        return responses.pop(0)

    monkeypatch.setattr("pixfabrica_api.compose_orchestrator.ollama_chat", fake_chat)

    result = run_compose_chat(session_id="sess-1", user_message="make a hello world")
    assert result.assistant_message == "Created a hello world composition."
    assert result.project == _HELLO
    assert result.context is not None
    assert result.context.prompt_tokens == 1100
    assert result.context.num_ctx == 32_768


def test_validate_graph_without_graph_uses_last_loaded_starter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = [
        {
            "message": _tool_call("load_builtin_example", {"name": "hello_world"}),
            "prompt_eval_count": 400,
        },
        {
            "message": _tool_call("validate_graph", {}),
            "prompt_eval_count": 700,
        },
        {
            "message": {
                "role": "assistant",
                "content": "The hello world project has been validated successfully.",
            },
            "prompt_eval_count": 900,
        },
    ]

    def fake_chat(**kwargs: Any) -> dict[str, Any]:
        return responses.pop(0)

    monkeypatch.setattr("pixfabrica_api.compose_orchestrator.ollama_chat", fake_chat)

    result = run_compose_chat(session_id="sess-2", user_message="make a hello world")
    assert result.project == _HELLO
