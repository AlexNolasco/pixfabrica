from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from pixfabrica_core.clips import CURRENT_SCHEMA_VERSION, RenderJob
from pixfabrica_core.errors import RenderError, RenderErrorCode


def parse_render_job_data(data: dict[str, Any]) -> RenderJob:
    """Validate a job dict and return a RenderJob."""
    job_version = data.get("schema_version", 1)
    if job_version != CURRENT_SCHEMA_VERSION:
        raise RenderError(
            RenderErrorCode.SCHEMA_VERSION_MISMATCH,
            {"job_version": job_version, "supported": CURRENT_SCHEMA_VERSION},
        )

    try:
        return RenderJob.model_validate(data)
    except ValidationError as exc:
        first = exc.errors()[0]
        field = ".".join(str(loc) for loc in first["loc"])
        raise RenderError(
            RenderErrorCode.INVALID_PARAMETER,
            {"field": field, "msg": first["msg"]},
        ) from exc


def load_render_job(path: Path) -> RenderJob:
    """Load and validate a RenderJob from a JSON file.

    Wraps Pydantic ValidationError into RenderError(INVALID_PARAMETER) and
    file/parse errors into RenderError(MISSING_ASSET) so callers always catch
    a single exception type.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RenderError(
            RenderErrorCode.MISSING_ASSET,
            {"path": str(path), "detail": str(exc)},
        ) from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RenderError(
            RenderErrorCode.INVALID_PARAMETER,
            {"field": "<json>", "msg": str(exc)},
        ) from exc

    if not isinstance(data, dict):
        raise RenderError(
            RenderErrorCode.INVALID_PARAMETER,
            {"field": "<json>", "msg": "job root must be an object"},
        )

    return parse_render_job_data(data)
