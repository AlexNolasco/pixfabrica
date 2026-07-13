"""Render job output directory."""

from __future__ import annotations

import os
from pathlib import Path

_ENV_JOBS_ROOT = "PIXFABRICA_JOBS_ROOT"
_DEFAULT_JOBS_ROOT = Path("jobs")

GRAPH_FILENAME = "graph.json"
METADATA_FILENAME = "metadata.json"
VIDEO_FILENAME = "video.mp4"


def jobs_root() -> Path:
    raw = os.environ.get(_ENV_JOBS_ROOT, "").strip()
    root = Path(raw) if raw else _DEFAULT_JOBS_ROOT
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()
