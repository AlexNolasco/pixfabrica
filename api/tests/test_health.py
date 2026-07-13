from fastapi.testclient import TestClient

from pixfabrica_api.main import app
from pixfabrica_api.ollama_settings import ComposeReadiness, OllamaHealth

client = TestClient(app)


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


def test_health(monkeypatch):
    monkeypatch.setattr("pixfabrica_api.main.shutil.which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr("pixfabrica_api.main.ollama_health", _compose_ready)
    monkeypatch.setattr("pixfabrica_api.main.pexels_available", lambda: False)
    monkeypatch.setattr(
        "pixfabrica_api.main.gl_capability_payload",
        lambda: {"gl_available": True, "gl_renderer": "Test GL"},
    )
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "ffmpeg": True,
        "gl": {"available": True, "reason": None, "renderer": "Test GL"},
        "ollama": True,
        "compose": {
            "model": "qwen2.5:14b",
            "model_available": True,
            "tools_capable": True,
            "ready": True,
            "reason": None,
        },
        "pexels_available": False,
        "version": "0.1.0",
    }


def test_health_degraded_without_ffmpeg(monkeypatch):
    monkeypatch.setattr("pixfabrica_api.main.shutil.which", lambda name: None)
    monkeypatch.setattr("pixfabrica_api.main.ollama_health", _compose_unavailable)
    monkeypatch.setattr("pixfabrica_api.main.pexels_available", lambda: False)
    monkeypatch.setattr(
        "pixfabrica_api.main.gl_capability_payload",
        lambda: {"gl_available": False, "gl_reason": "no context"},
    )
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "degraded",
        "ffmpeg": False,
        "gl": {"available": False, "reason": "no context", "renderer": None},
        "ollama": False,
        "compose": {
            "model": "qwen2.5:14b",
            "model_available": False,
            "tools_capable": None,
            "ready": False,
            "reason": "ollama_unreachable",
        },
        "pexels_available": False,
        "version": "0.1.0",
    }
