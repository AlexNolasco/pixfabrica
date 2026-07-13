from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from pixfabrica_api.compose_orchestrator import ComposeChatResult, ComposeContextUsage
from pixfabrica_api.main import app
from pixfabrica_api.ollama_settings import ComposeReadiness, OllamaHealth

client = TestClient(app)
AUTH = {"Authorization": "Bearer pixfabrica-dev-token"}
_REPO = Path(__file__).resolve().parents[2]
_HELLO = json.loads((_REPO / "cli" / "examples" / "hello_world.json").read_text(encoding="utf-8"))


def _compose_ready() -> OllamaHealth:
    return OllamaHealth(
        available=True,
        compose=ComposeReadiness(
            model="qwen2.5:14b",
            model_available=True,
            tools_capable=True,
            ready=True,
            reason=None,
        ),
    )


def _compose_unavailable() -> OllamaHealth:
    return OllamaHealth(
        available=False,
        compose=ComposeReadiness(
            model="qwen2.5:14b",
            model_available=False,
            tools_capable=None,
            ready=False,
            reason="ollama_unreachable",
        ),
    )


def test_compose_chat_requires_auth() -> None:
    response = client.post("/compose/chat", json={"message": "make a hello world"})
    assert response.status_code == 401


def test_compose_chat_503_when_compose_not_ready(monkeypatch) -> None:
    monkeypatch.setattr("pixfabrica_api.routes.compose.ollama_health", _compose_unavailable)
    response = client.post(
        "/compose/chat",
        json={"message": "make a hello world"},
        headers=AUTH,
    )
    assert response.status_code == 503
    assert response.json() == {
        "detail": {
            "code": "compose_unavailable",
            "model": "qwen2.5:14b",
            "reason": "ollama_unreachable",
        }
    }


def test_compose_chat_returns_project_when_orchestrator_succeeds(monkeypatch) -> None:
    monkeypatch.setattr("pixfabrica_api.routes.compose.ollama_health", _compose_ready)

    def fake_run_compose_chat(**kwargs):
        return ComposeChatResult(
            session_id=kwargs["session_id"],
            assistant_message="Created a hello world composition.",
            project=_HELLO,
            applied=False,
            context=ComposeContextUsage(prompt_tokens=1100, num_ctx=32768),
        )

    monkeypatch.setattr("pixfabrica_api.routes.compose.run_compose_chat", fake_run_compose_chat)
    response = client.post(
        "/compose/chat",
        json={"session_id": "sess-test", "message": "make a hello world"},
        headers=AUTH,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "sess-test"
    assert data["assistant_message"] == "Created a hello world composition."
    assert data["project"]["title"] == "Hello, World!"
    assert data["context"]["prompt_tokens"] == 1100
    assert data["context"]["num_ctx"] == 32768


def test_compose_chat_502_when_ollama_chat_fails(monkeypatch) -> None:
    monkeypatch.setattr("pixfabrica_api.routes.compose.ollama_health", _compose_ready)

    from pixfabrica_api.ollama_compose_client import OllamaComposeError

    def fake_run_compose_chat(**kwargs):
        raise OllamaComposeError("connection refused")

    monkeypatch.setattr("pixfabrica_api.routes.compose.run_compose_chat", fake_run_compose_chat)
    response = client.post(
        "/compose/chat",
        json={"message": "make a hello world"},
        headers=AUTH,
    )
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "ollama_chat_failed"


def test_compose_chat_rejects_empty_message(monkeypatch) -> None:
    monkeypatch.setattr("pixfabrica_api.routes.compose.ollama_health", _compose_ready)
    response = client.post("/compose/chat", json={"message": ""}, headers=AUTH)
    assert response.status_code == 422


def test_delete_compose_session_requires_auth() -> None:
    response = client.delete("/compose/sessions/sess-1")
    assert response.status_code == 401


def test_delete_compose_session_drops_server_context(monkeypatch) -> None:
    from pixfabrica_api.compose_orchestrator import (
        _session_for,
        delete_compose_session,
        reset_compose_sessions,
    )

    reset_compose_sessions()
    _session_for("sess-drop")
    assert delete_compose_session("sess-drop") is True

    response = client.delete("/compose/sessions/sess-drop", headers=AUTH)
    assert response.status_code == 200
    assert response.json() == {"deleted": False}

    _session_for("sess-drop-2")
    response = client.delete("/compose/sessions/sess-drop-2", headers=AUTH)
    assert response.status_code == 200
    assert response.json() == {"deleted": True}
    assert delete_compose_session("sess-drop-2") is False
