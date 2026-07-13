"""Ollama /api/chat client for compose agent loops."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from pixfabrica_api.ollama_settings import (
    compose_chat_timeout_seconds,
    compose_keep_alive,
    compose_num_predict,
    ollama_base_url,
)


class OllamaComposeError(Exception):
    """Raised when Ollama chat fails."""


def ollama_chat(
    *,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    num_ctx: int,
) -> dict[str, Any]:
    """Call Ollama ``POST /api/chat`` and return the parsed response object."""
    url = f"{ollama_base_url()}/api/chat"
    payload = {
        "model": model,
        "messages": messages,
        "tools": tools,
        "stream": False,
        "keep_alive": compose_keep_alive(),
        "options": {
            "num_ctx": num_ctx,
            "num_predict": compose_num_predict(),
            "temperature": 0.2,
        },
    }
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    timeout = compose_chat_timeout_seconds()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                raise OllamaComposeError(f"ollama chat failed with status {response.status}")
            raw = response.read()
    except OllamaComposeError:
        raise
    except (OSError, urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise OllamaComposeError("ollama chat request failed") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise OllamaComposeError("ollama chat returned invalid JSON") from exc
    if not isinstance(data, dict):
        raise OllamaComposeError("ollama chat returned unexpected payload")
    return data
