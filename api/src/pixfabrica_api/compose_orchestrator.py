"""Compose chat orchestrator — Ollama tool loop with in-memory sessions."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from pixfabrica_api.compose_theme import apply_job_theme_to_graph, normalize_editor_job_context
from pixfabrica_api.compose_tools import compose_tool_definitions, execute_compose_tool
from pixfabrica_api.ollama_compose_client import OllamaComposeError, ollama_chat
from pixfabrica_api.ollama_settings import compose_max_turns, compose_model, compose_num_ctx

log = logging.getLogger("pixfabrica.api.compose")

_SYSTEM_PROMPT = """\
You compose Pixfabrica video projects for the timeline editor.

Each tool round is a full model inference — keep the chain short (aim for 4–5 passes):
1. list_catalog_clips once (includes defaults per clip) — skip get_clip_detail unless you need non-default params
2. build_graph with a compact spec, or load_builtin_example for built-in demos only
3. apply_job_theme — use_editor_theme to match <editor_job_context> unless the user asked for a different preset (list_theme_presets)
4. validate_graph with no graph argument (validates the last draft)
5. Brief plain-language reply to the user

Theme rules:
- Prefer theme tokens on clip params (primary, accent, background, …) not raw hex.
- editor_job_context on the user message is the current editor palette snapshot (read-only).
- To change only colors on an existing draft, apply_job_theme then validate_graph.

Layout (readability):
- One hero text per scene; do not stack multiple text clips at the same offset (0.5, 0.5).
- Stagger track.start so one full-frame skia/gl track dominates unless using transition_in/out.
- clips order: background first, text last (top). Title ~offset_y 0.35, subtitle ~0.65.
- If validate_graph returns warnings, fix the graph and validate again before replying.

Typography:
- Set typography_role on text clips — do not invent font sizes (see list_typography_roles).
- One display_large or title_large hero per scene; label_medium for artist/album metadata below.
- body_* for sentences/lyrics; mono_* for data/debug only — not main titles.

Track backend (strict):
- Skia clips (text, 2D backgrounds, video) go ONLY on track_kind skia (std-skia-track).
- GL clips (shaders, particles, GPU effects) go ONLY on track_kind gl (std-gl-track).
- Post/effect clips go ONLY on track_kind post (std-post-track).
- list_catalog_clips includes track_kind per clip — match it exactly when building tracks.

Rules:
- Prefer build_graph with tracks + clips for custom compositions.
- load_builtin_example is only for hello_world and hello_world_transitions.
- Do not invent clip types or hand-write full project JSON.
"""


@dataclass
class ComposeContextUsage:
    prompt_tokens: int
    num_ctx: int

    @property
    def fill_ratio(self) -> float:
        if self.num_ctx <= 0:
            return 0.0
        return min(1.0, self.prompt_tokens / self.num_ctx)


@dataclass
class ComposeTiming:
    elapsed_ms: int
    ollama_calls: int
    eval_ms: int | None = None


@dataclass
class ComposeChatResult:
    session_id: str
    assistant_message: str
    project: dict[str, Any] | None = None
    applied: bool = False
    context: ComposeContextUsage | None = None
    timing: ComposeTiming | None = None


@dataclass
class _ComposeSession:
    messages: list[dict[str, Any]] = field(default_factory=list)
    last_graph_draft: dict[str, Any] | None = None
    last_validated_project: dict[str, Any] | None = None
    editor_job_context: dict[str, Any] | None = None


_sessions: dict[str, _ComposeSession] = {}


def _session_for(session_id: str) -> _ComposeSession:
    session = _sessions.get(session_id)
    if session is None:
        session = _ComposeSession(
            messages=[{"role": "system", "content": _SYSTEM_PROMPT}],
        )
        _sessions[session_id] = session
    return session


def reset_compose_sessions() -> None:
    """Clear in-memory sessions (tests)."""
    _sessions.clear()


def delete_compose_session(session_id: str) -> bool:
    """Drop one compose session and its message history. Returns True if it existed."""
    return _sessions.pop(session_id, None) is not None


def _parse_tool_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return {}
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("tool arguments must be a JSON object")
    return parsed


def _tool_calls_from_message(message: dict[str, Any]) -> list[dict[str, Any]]:
    tool_calls = message.get("tool_calls")
    if not isinstance(tool_calls, list):
        return []
    return [call for call in tool_calls if isinstance(call, dict)]


def _assistant_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    return ""


def _user_message_with_context(message: str, editor_job_context: dict[str, Any] | None) -> str:
    if not editor_job_context:
        return message
    payload = json.dumps(editor_job_context, separators=(",", ":"))
    return f"{message}\n\n<editor_job_context>\n{payload}\n</editor_job_context>"


def _run_tool(session: _ComposeSession, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "apply_job_theme":
        graph = session.last_graph_draft
        if not isinstance(graph, dict):
            return {
                "ok": False,
                "errors": ["no graph draft — build_graph or load_builtin_example first"],
            }
        result = apply_job_theme_to_graph(
            graph,
            arguments,
            editor_job_context=session.editor_job_context,
        )
        if result.get("ok"):
            updated = result.get("graph")
            if isinstance(updated, dict):
                session.last_graph_draft = updated
            return {
                "ok": True,
                "palette_source": result.get("palette_source"),
            }
        return result

    if name == "validate_graph":
        from pixfabrica_api.compose_graph import validate_graph_for_compose

        graph = arguments.get("graph")
        if not isinstance(graph, dict):
            graph = session.last_graph_draft
        if not isinstance(graph, dict):
            return {
                "ok": False,
                "errors": ["no graph to validate — call load_builtin_example first"],
            }
        result = validate_graph_for_compose(graph)
        if result.get("ok"):
            session.last_validated_project = graph
        return result

    result = execute_compose_tool(name, arguments)
    if name in ("load_builtin_example", "build_graph") and result.get("ok"):
        loaded = result.get("graph")
        if isinstance(loaded, dict):
            session.last_graph_draft = loaded
    return result


def run_compose_chat(
    *,
    session_id: str,
    user_message: str,
    job_context: dict[str, Any] | None = None,
) -> ComposeChatResult:
    """Run one compose chat turn (may include multiple Ollama tool round-trips)."""
    session = _session_for(session_id)
    if job_context is not None:
        session.editor_job_context = normalize_editor_job_context(job_context)
    session.messages.append(
        {
            "role": "user",
            "content": _user_message_with_context(user_message, session.editor_job_context),
        }
    )

    model = compose_model()
    num_ctx = compose_num_ctx()
    tools = compose_tool_definitions()
    last_prompt_tokens = 0
    assistant_message = ""
    started = time.perf_counter()
    ollama_calls = 0
    eval_ns_total = 0

    for _turn in range(compose_max_turns()):
        try:
            response = ollama_chat(
                model=model,
                messages=session.messages,
                tools=tools,
                num_ctx=num_ctx,
            )
        except OllamaComposeError as exc:
            log.warning("compose ollama chat failed: %s", exc)
            raise

        ollama_calls += 1
        eval_duration = response.get("eval_duration")
        if isinstance(eval_duration, (int, float)) and eval_duration > 0:
            eval_ns_total += int(eval_duration)

        last_prompt_tokens = int(response.get("prompt_eval_count") or 0)
        message = response.get("message")
        if not isinstance(message, dict):
            raise OllamaComposeError("ollama chat response missing message")

        session.messages.append(message)
        tool_calls = _tool_calls_from_message(message)
        if tool_calls:
            for call in tool_calls:
                function = call.get("function")
                if not isinstance(function, dict):
                    continue
                name = function.get("name")
                if not isinstance(name, str) or not name:
                    continue
                try:
                    arguments = _parse_tool_arguments(function.get("arguments"))
                    result = _run_tool(session, name, arguments)
                    content = json.dumps(result)
                except (json.JSONDecodeError, ValueError, OSError) as exc:
                    content = json.dumps({"ok": False, "errors": [str(exc)]})
                session.messages.append(
                    {
                        "role": "tool",
                        "tool_name": name,
                        "content": content,
                    }
                )
            continue

        assistant_message = _assistant_text(message)
        break
    else:
        assistant_message = "I could not finish composing within the allowed number of tool steps."

    if not assistant_message:
        if session.last_validated_project is not None:
            title = session.last_validated_project.get("title") or "project"
            assistant_message = f"Created {title!s}."
        else:
            assistant_message = "I could not produce a validated composition."

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    eval_ms = int(eval_ns_total / 1_000_000) if eval_ns_total else None
    log.info(
        "compose session=%s ollama_calls=%d elapsed_ms=%d eval_ms=%s prompt_tokens=%d",
        session_id,
        ollama_calls,
        elapsed_ms,
        eval_ms if eval_ms is not None else "-",
        last_prompt_tokens,
    )

    return ComposeChatResult(
        session_id=session_id,
        assistant_message=assistant_message,
        project=session.last_validated_project,
        applied=False,
        context=ComposeContextUsage(prompt_tokens=last_prompt_tokens, num_ctx=num_ctx),
        timing=ComposeTiming(
            elapsed_ms=elapsed_ms,
            ollama_calls=ollama_calls,
            eval_ms=eval_ms,
        ),
    )
