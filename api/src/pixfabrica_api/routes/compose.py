"""Compose chat endpoints (agent-driven project generation)."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from pixfabrica_api.compose_orchestrator import delete_compose_session, run_compose_chat
from pixfabrica_api.ollama_compose_client import OllamaComposeError
from pixfabrica_api.ollama_settings import ComposeReadiness, ollama_health

router = APIRouter(prefix="/compose", tags=["compose"])


class ComposeJobContextRequest(BaseModel):
    """Snapshot of the editor job theme sent with each compose message."""

    colors: dict[str, str] | None = Field(
        default=None,
        description="Resolved job palette (primary, accent, background, …)",
    )
    palette_source: dict[str, Any] | None = Field(
        default=None,
        description="Named preset, extracted, or custom palette source",
    )


class ComposeChatRequest(BaseModel):
    session_id: str | None = Field(
        default=None,
        description="Optional client session id; a new id is issued when omitted",
    )
    message: str = Field(min_length=1, description="User message for the compose agent")
    job_context: ComposeJobContextRequest | None = Field(
        default=None,
        description="Current editor colors/palette snapshot for theme-aware composition",
    )


class ComposeContextResponse(BaseModel):
    prompt_tokens: int
    num_ctx: int
    fill_ratio: float


class ComposeTimingResponse(BaseModel):
    elapsed_ms: int
    ollama_calls: int
    eval_ms: int | None = None


class ComposeChatResponse(BaseModel):
    session_id: str
    assistant_message: str
    project: dict[str, Any] | None = None
    applied: bool = False
    context: ComposeContextResponse | None = None
    timing: ComposeTimingResponse | None = None


def require_compose_ready() -> ComposeReadiness:
    """Raise 503 when Ollama or the configured compose model is not ready."""
    compose = ollama_health().compose
    if compose.ready:
        return compose
    raise HTTPException(
        status_code=503,
        detail={
            "code": "compose_unavailable",
            "model": compose.model,
            "reason": compose.reason,
        },
    )


class ComposeSessionDeleteResponse(BaseModel):
    deleted: bool


@router.delete("/sessions/{session_id}", response_model=ComposeSessionDeleteResponse)
async def delete_compose_session_route(session_id: str) -> ComposeSessionDeleteResponse:
    """Release server-side compose context for a session (e.g. when the user starts a new chat)."""
    session_id = session_id.strip()
    if not session_id:
        raise HTTPException(status_code=422, detail="session_id required")
    return ComposeSessionDeleteResponse(deleted=delete_compose_session(session_id))


@router.post("/chat", response_model=ComposeChatResponse)
async def compose_chat(body: ComposeChatRequest) -> ComposeChatResponse:
    require_compose_ready()
    session_id = body.session_id.strip() if body.session_id else ""
    if not session_id:
        session_id = str(uuid.uuid4())

    job_context = None
    if body.job_context is not None:
        job_context = body.job_context.model_dump(exclude_none=True)

    try:
        # Ollama calls are sync/blocking — run off the event loop so /health stays responsive.
        result = await asyncio.to_thread(
            run_compose_chat,
            session_id=session_id,
            user_message=body.message,
            job_context=job_context,
        )
    except OllamaComposeError as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": "ollama_chat_failed", "message": str(exc)},
        ) from exc

    context = None
    if result.context is not None:
        context = ComposeContextResponse(
            prompt_tokens=result.context.prompt_tokens,
            num_ctx=result.context.num_ctx,
            fill_ratio=result.context.fill_ratio,
        )

    timing = None
    if result.timing is not None:
        timing = ComposeTimingResponse(
            elapsed_ms=result.timing.elapsed_ms,
            ollama_calls=result.timing.ollama_calls,
            eval_ms=result.timing.eval_ms,
        )

    return ComposeChatResponse(
        session_id=result.session_id,
        assistant_message=result.assistant_message,
        project=result.project,
        applied=result.applied,
        context=context,
        timing=timing,
    )
