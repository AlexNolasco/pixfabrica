"""Ollama host detection for future compose / agent features."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

_DEFAULT_BASE_URL = "http://127.0.0.1:11434"
_DEFAULT_COMPOSE_MODEL = "qwen2.5:14b"
_DEFAULT_COMPOSE_NUM_CTX = 32_768
_DEFAULT_COMPOSE_NUM_PREDICT = 4096
_DEFAULT_COMPOSE_KEEP_ALIVE = "30m"
_PROBE_TIMEOUT_SECONDS = 2.0
_CHAT_TIMEOUT_SECONDS = 120.0
_MAX_COMPOSE_TURNS = 10


@dataclass(frozen=True, slots=True)
class ComposeReadiness:
    model: str
    model_available: bool
    tools_capable: bool | None
    ready: bool
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class OllamaHealth:
    available: bool
    compose: ComposeReadiness


def ollama_base_url() -> str:
    """Resolve Ollama HTTP base URL from env.

    ``PIXFABRICA_OLLAMA_BASE_URL`` overrides ``OLLAMA_HOST`` (Ollama's own env var).
    Values may be ``host:port`` or a full ``http(s)://`` URL.
    """
    for key in ("PIXFABRICA_OLLAMA_BASE_URL", "OLLAMA_HOST"):
        raw = os.environ.get(key, "").strip()
        if raw:
            return _normalize_base_url(raw)
    return _DEFAULT_BASE_URL


def compose_model() -> str:
    """Configured compose model (``PIXFABRICA_COMPOSE_MODEL``)."""
    raw = os.environ.get("PIXFABRICA_COMPOSE_MODEL", "").strip()
    return raw or _DEFAULT_COMPOSE_MODEL


def compose_num_ctx() -> int:
    """Context window for compose chat (``PIXFABRICA_COMPOSE_NUM_CTX``)."""
    raw = os.environ.get("PIXFABRICA_COMPOSE_NUM_CTX", "").strip()
    if not raw:
        return _DEFAULT_COMPOSE_NUM_CTX
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_COMPOSE_NUM_CTX
    return max(2048, value)


def compose_num_predict() -> int:
    """Max tokens generated per Ollama round (``PIXFABRICA_COMPOSE_NUM_PREDICT``)."""
    raw = os.environ.get("PIXFABRICA_COMPOSE_NUM_PREDICT", "").strip()
    if not raw:
        return _DEFAULT_COMPOSE_NUM_PREDICT
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_COMPOSE_NUM_PREDICT
    return max(256, value)


def compose_keep_alive() -> str:
    """Ollama model keep-alive between compose round-trips."""
    raw = os.environ.get("PIXFABRICA_COMPOSE_KEEP_ALIVE", "").strip()
    return raw or _DEFAULT_COMPOSE_KEEP_ALIVE


def compose_max_turns() -> int:
    """Maximum Ollama round-trips per user message."""
    raw = os.environ.get("PIXFABRICA_COMPOSE_MAX_TURNS", "").strip()
    if not raw:
        return _MAX_COMPOSE_TURNS
    try:
        value = int(raw)
    except ValueError:
        return _MAX_COMPOSE_TURNS
    return max(1, min(value, 32))


def compose_chat_timeout_seconds() -> float:
    raw = os.environ.get("PIXFABRICA_COMPOSE_TIMEOUT", "").strip()
    if not raw:
        return _CHAT_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return _CHAT_TIMEOUT_SECONDS
    return max(5.0, value)


def _normalize_base_url(raw: str) -> str:
    value = raw.strip().rstrip("/")
    if not value:
        return _DEFAULT_BASE_URL
    if "://" not in value:
        value = f"http://{value}"
    return value


def _fetch_ollama_tags() -> dict[str, Any] | None:
    url = f"{ollama_base_url()}/api/tags"
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=_PROBE_TIMEOUT_SECONDS) as response:
            if response.status != 200:
                return None
            body = response.read()
    except (OSError, urllib.error.URLError, TimeoutError, ValueError):
        return None
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _find_installed_model(models: list[Any], model_name: str) -> dict[str, Any] | None:
    for entry in models:
        if not isinstance(entry, dict):
            continue
        for key in ("name", "model"):
            value = entry.get(key)
            if isinstance(value, str) and value == model_name:
                return entry
    return None


def _compose_readiness_from_tags(payload: dict[str, Any] | None) -> ComposeReadiness:
    model_name = compose_model()
    if payload is None:
        return ComposeReadiness(
            model=model_name,
            model_available=False,
            tools_capable=None,
            ready=False,
            reason="ollama_unreachable",
        )

    models = payload.get("models")
    if not isinstance(models, list):
        return ComposeReadiness(
            model=model_name,
            model_available=False,
            tools_capable=None,
            ready=False,
            reason="invalid_tags_response",
        )

    installed = _find_installed_model(models, model_name)
    if installed is None:
        return ComposeReadiness(
            model=model_name,
            model_available=False,
            tools_capable=None,
            ready=False,
            reason="model_not_installed",
        )

    capabilities = installed.get("capabilities")
    if not isinstance(capabilities, list):
        return ComposeReadiness(
            model=model_name,
            model_available=True,
            tools_capable=None,
            ready=False,
            reason="tools_capability_unknown",
        )

    tools_capable = "tools" in capabilities
    if not tools_capable:
        return ComposeReadiness(
            model=model_name,
            model_available=True,
            tools_capable=False,
            ready=False,
            reason="tools_not_supported",
        )

    return ComposeReadiness(
        model=model_name,
        model_available=True,
        tools_capable=True,
        ready=True,
        reason=None,
    )


def ollama_health() -> OllamaHealth:
    """Single ``/api/tags`` probe for daemon and compose readiness."""
    payload = _fetch_ollama_tags()
    available = payload is not None and isinstance(payload.get("models"), list)
    return OllamaHealth(available=available, compose=_compose_readiness_from_tags(payload))


def ollama_available() -> bool:
    """True when the Ollama HTTP API responds on ``GET /api/tags``."""
    return ollama_health().available
