from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path
from typing import Any

_LOCALE_DIR = Path(__file__).parent / "locale"


class RenderErrorCode(StrEnum):
    UNKNOWN_PLUGIN = "unknown_plugin"
    INVALID_PARAMETER = "invalid_parameter"
    MISSING_ASSET = "missing_asset"
    FFMPEG_FAILURE = "ffmpeg_failure"
    ANALYSIS_FAILED = "analysis_failed"
    CANCELLED = "cancelled"
    OUTPUT_WRITE_ERROR = "output_write_error"
    SCHEMA_VERSION_MISMATCH = "schema_version_mismatch"
    GL_UNAVAILABLE = "gl_unavailable"


class RenderError(Exception):
    def __init__(self, code: RenderErrorCode, context: dict[str, Any] | None = None) -> None:
        self.code = code
        self.context: dict[str, Any] = context or {}
        super().__init__(str(code))

    def format(self, locale: str = "en") -> str:
        """Return a localised human-readable message."""
        locale_file = _LOCALE_DIR / f"errors.{locale}.json"
        if not locale_file.exists():
            locale_file = _LOCALE_DIR / "errors.en.json"
        messages: dict[str, str] = json.loads(locale_file.read_text(encoding="utf-8"))
        template = messages.get(self.code, str(self.code))
        ctx = dict(self.context)
        if "clip_type" not in ctx:
            for key in ("setting_type", "sound_type", "effect_type"):
                if key in ctx:
                    ctx["clip_type"] = ctx[key]
                    break
        try:
            return template.format(**ctx)
        except KeyError:
            return template
