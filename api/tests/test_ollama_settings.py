from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from pixfabrica_api import ollama_settings


def test_ollama_base_url_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PIXFABRICA_OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    assert ollama_settings.ollama_base_url() == "http://127.0.0.1:11434"


def test_ollama_base_url_prefers_pixfabrica_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PIXFABRICA_OLLAMA_BASE_URL", "http://ollama.internal:11434/")
    monkeypatch.setenv("OLLAMA_HOST", "ignored:9999")
    assert ollama_settings.ollama_base_url() == "http://ollama.internal:11434"


def test_ollama_base_url_normalizes_ollama_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PIXFABRICA_OLLAMA_BASE_URL", raising=False)
    monkeypatch.setenv("OLLAMA_HOST", "192.168.1.50:11434")
    assert ollama_settings.ollama_base_url() == "http://192.168.1.50:11434"


def test_ollama_available_true_when_tags_responds(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.dumps({"models": []}).encode()

    def fake_urlopen(request, timeout=0):  # noqa: ANN001, ARG001
        assert request.full_url.endswith("/api/tags")
        response = MagicMock()
        response.status = 200
        response.read.return_value = payload
        response.__enter__ = lambda self: self
        response.__exit__ = lambda *args: None
        return response

    monkeypatch.setattr(ollama_settings.urllib.request, "urlopen", fake_urlopen)
    assert ollama_settings.ollama_available() is True


def test_ollama_available_false_on_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request, timeout=0):  # noqa: ANN001, ARG001
        raise OSError("connection refused")

    monkeypatch.setattr(ollama_settings.urllib.request, "urlopen", fake_urlopen)
    assert ollama_settings.ollama_available() is False


def test_ollama_available_false_on_invalid_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request, timeout=0):  # noqa: ANN001, ARG001
        response = MagicMock()
        response.status = 200
        response.read.return_value = b"not-json"
        response.__enter__ = lambda self: self
        response.__exit__ = lambda *args: None
        return response

    monkeypatch.setattr(ollama_settings.urllib.request, "urlopen", fake_urlopen)
    assert ollama_settings.ollama_available() is False


def test_compose_model_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PIXFABRICA_COMPOSE_MODEL", raising=False)
    assert ollama_settings.compose_model() == "qwen2.5:14b"


def test_compose_model_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PIXFABRICA_COMPOSE_MODEL", "qwen3.6:35b-a3b")
    assert ollama_settings.compose_model() == "qwen3.6:35b-a3b"


def test_compose_num_ctx_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PIXFABRICA_COMPOSE_NUM_CTX", raising=False)
    assert ollama_settings.compose_num_ctx() == 32_768


def test_compose_num_ctx_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PIXFABRICA_COMPOSE_NUM_CTX", "8192")
    assert ollama_settings.compose_num_ctx() == 8192


def test_compose_readiness_ready_when_model_supports_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PIXFABRICA_COMPOSE_MODEL", raising=False)
    payload = json.dumps(
        {
            "models": [
                {
                    "name": "qwen2.5:14b",
                    "model": "qwen2.5:14b",
                    "capabilities": ["completion", "tools"],
                }
            ]
        }
    ).encode()

    def fake_urlopen(request, timeout=0):  # noqa: ANN001, ARG001
        response = MagicMock()
        response.status = 200
        response.read.return_value = payload
        response.__enter__ = lambda self: self
        response.__exit__ = lambda *args: None
        return response

    monkeypatch.setattr(ollama_settings.urllib.request, "urlopen", fake_urlopen)
    health = ollama_settings.ollama_health()
    assert health.available is True
    assert health.compose.ready is True
    assert health.compose.model == "qwen2.5:14b"
    assert health.compose.tools_capable is True


def test_compose_readiness_model_not_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PIXFABRICA_COMPOSE_MODEL", "missing:7b")
    payload = json.dumps({"models": []}).encode()

    def fake_urlopen(request, timeout=0):  # noqa: ANN001, ARG001
        response = MagicMock()
        response.status = 200
        response.read.return_value = payload
        response.__enter__ = lambda self: self
        response.__exit__ = lambda *args: None
        return response

    monkeypatch.setattr(ollama_settings.urllib.request, "urlopen", fake_urlopen)
    health = ollama_settings.ollama_health()
    assert health.compose.ready is False
    assert health.compose.reason == "model_not_installed"


def test_compose_readiness_tools_not_supported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PIXFABRICA_COMPOSE_MODEL", "legacy:7b")
    payload = json.dumps(
        {
            "models": [
                {
                    "name": "legacy:7b",
                    "model": "legacy:7b",
                    "capabilities": ["completion"],
                }
            ]
        }
    ).encode()

    def fake_urlopen(request, timeout=0):  # noqa: ANN001, ARG001
        response = MagicMock()
        response.status = 200
        response.read.return_value = payload
        response.__enter__ = lambda self: self
        response.__exit__ = lambda *args: None
        return response

    monkeypatch.setattr(ollama_settings.urllib.request, "urlopen", fake_urlopen)
    health = ollama_settings.ollama_health()
    assert health.compose.model_available is True
    assert health.compose.tools_capable is False
    assert health.compose.ready is False
    assert health.compose.reason == "tools_not_supported"
