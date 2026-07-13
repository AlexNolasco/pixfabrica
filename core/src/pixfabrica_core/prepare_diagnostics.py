"""Collect non-fatal asset resolution failures during clip prepare (preview diagnostics)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

PrepareWarningKind = Literal["clip", "sound"]


def _normalize_warning_kind(kind: str) -> PrepareWarningKind:
    if kind == "clip":
        return "clip"
    if kind == "sound":
        return "sound"
    raise ValueError(f"unknown prepare warning kind: {kind!r}")


@dataclass(frozen=True, slots=True)
class PrepareWarning:
    kind: PrepareWarningKind
    ref_id: str
    clip_type: str
    field: str
    source: str
    code: str
    message: str


def format_asset_error(exc: BaseException) -> str:
    """Human-readable detail; include HTTP status when available."""
    try:
        import httpx
    except ImportError:
        httpx = None  # type: ignore[assignment]

    if httpx is not None and isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    text = str(exc).strip()
    return text if text else type(exc).__name__


@dataclass
class PrepareDiagnostics:
    _items: list[PrepareWarning] = field(default_factory=list)

    def record_asset_failure(
        self,
        *,
        kind: str,
        ref_id: str,
        clip_type: str,
        field: str,
        source: str,
        exc: BaseException,
        code: str = "resolve_failed",
    ) -> None:
        trimmed = source.strip()
        if not trimmed:
            return
        self._items.append(
            PrepareWarning(
                kind=_normalize_warning_kind(kind),
                ref_id=ref_id,
                clip_type=clip_type,
                field=field,
                source=trimmed,
                code=code,
                message=format_asset_error(exc),
            )
        )

    def ingest(self, warnings: list[PrepareWarning]) -> None:
        if warnings:
            self._items.extend(warnings)

    def items(self) -> list[PrepareWarning]:
        return list(self._items)

    def to_wire_items(self) -> list[dict[str, str]]:
        return [
            {
                "kind": w.kind,
                "ref_id": w.ref_id,
                "clip_type": w.clip_type,
                "field": w.field,
                "source": w.source,
                "code": w.code,
                "message": w.message,
            }
            for w in self._items
        ]


def record_prepare_asset_failure(
    ctx: Any,
    *,
    kind: str,
    ref_id: str,
    clip_type: str,
    field: str,
    source: str,
    exc: BaseException,
    code: str = "resolve_failed",
) -> None:
    """Record a missing/unreachable asset when diagnostics are attached to prepare."""
    if ctx.diagnostics is None:
        return
    ctx.diagnostics.record_asset_failure(
        kind=kind,
        ref_id=ref_id,
        clip_type=clip_type,
        field=field,
        source=source,
        exc=exc,
        code=code,
    )


def prepare_warnings_event(diagnostics: PrepareDiagnostics) -> dict[str, Any]:
    return {"event": "prepare_warnings", "items": diagnostics.to_wire_items()}
