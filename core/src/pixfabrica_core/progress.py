from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class RenderProgress(BaseModel):
    stage: Literal["prepare", "render", "done", "cancelled"]
    frame: int = 0
    total: int = 0
    pct: int = 0
    parallelism_effective: Literal["single", "multi"] | None = None
