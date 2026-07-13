"""Theme helpers for the compose agent."""

from __future__ import annotations

import copy
import re
from typing import Any

from pixfabrica_core.theme.color import ColorToken
from pixfabrica_core.theme.presets import (
    THEME_ORDER,
    get_named_palette,
    list_theme_presets,
    palette_to_hex_dict,
)

_HEX_RE = re.compile(r"^#([0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
_TOKEN_KEYS = frozenset(token.value for token in ColorToken)
_THEME_NAMES = frozenset(THEME_ORDER)
_VARIANTS = frozenset(("dark", "light"))


def list_theme_presets_for_compose() -> dict[str, Any]:
    """Compact preset catalog for compose tools (labels only — use apply_job_theme to apply)."""
    presets = [
        {
            "theme": row["theme"],
            "variant": row["variant"],
            "label": row["label"],
        }
        for row in list_theme_presets()
    ]
    return {"ok": True, "count": len(presets), "presets": presets}


def _parse_colors(raw: Any) -> dict[str, str] | None:
    if not isinstance(raw, dict):
        return None
    colors: dict[str, str] = {}
    for key in _TOKEN_KEYS:
        value = raw.get(key)
        if not isinstance(value, str) or not _HEX_RE.match(value):
            return None
        colors[key] = value
    return colors


def _parse_palette_source(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    source_type = raw.get("type")
    if source_type == "named":
        theme = raw.get("theme")
        variant = raw.get("variant")
        if not isinstance(theme, str) or theme not in _THEME_NAMES:
            return None
        if variant not in _VARIANTS:
            return None
        return {"type": "named", "theme": theme, "variant": variant}
    if source_type == "extracted":
        entry: dict[str, Any] = {"type": "extracted"}
        filename = raw.get("filename")
        if isinstance(filename, str) and filename.strip():
            entry["filename"] = filename.strip()
        return entry
    if source_type == "custom":
        return {"type": "custom"}
    return None


def normalize_editor_job_context(raw: Any) -> dict[str, Any] | None:
    """Validate client job_context snapshot (colors + palette_source)."""
    if not isinstance(raw, dict):
        return None
    colors = _parse_colors(raw.get("colors"))
    palette_source = _parse_palette_source(raw.get("palette_source"))
    if colors is None and palette_source is None:
        return None
    ctx: dict[str, Any] = {}
    if colors is not None:
        ctx["colors"] = colors
    if palette_source is not None:
        ctx["palette_source"] = palette_source
    return ctx or None


def _merge_color_overrides(base: dict[str, str], overrides: dict[str, Any]) -> dict[str, str]:
    merged = dict(base)
    for key, value in overrides.items():
        if key not in _TOKEN_KEYS:
            raise ValueError(f"unknown color token: {key}")
        if not isinstance(value, str) or not _HEX_RE.match(value):
            raise ValueError(f"invalid hex for {key}")
        merged[key] = value
    return merged


def apply_job_theme_to_graph(
    graph: dict[str, Any],
    arguments: dict[str, Any],
    *,
    editor_job_context: dict[str, Any] | None,
) -> dict[str, Any]:
    """Apply job-level theme fields to a project graph dict."""
    updated = copy.deepcopy(graph)
    use_editor = arguments.get("use_editor_theme") is True
    theme = arguments.get("theme")
    variant = arguments.get("variant")
    color_overrides = arguments.get("colors")

    if use_editor:
        if editor_job_context is None or "colors" not in editor_job_context:
            return {
                "ok": False,
                "errors": ["no editor theme — client must send job_context or use theme+variant"],
            }
        updated["colors"] = copy.deepcopy(editor_job_context["colors"])
        palette_source = editor_job_context.get("palette_source")
        updated["palette_source"] = (
            copy.deepcopy(palette_source)
            if isinstance(palette_source, dict)
            else {"type": "custom"}
        )
    elif isinstance(theme, str) and isinstance(variant, str):
        theme_key = theme.strip().lower()
        variant_key = variant.strip().lower()
        if theme_key not in _THEME_NAMES:
            known = ", ".join(sorted(_THEME_NAMES))
            return {"ok": False, "errors": [f"unknown theme {theme!r}; known: {known}"]}
        if variant_key not in _VARIANTS:
            return {"ok": False, "errors": ["variant must be dark or light"]}
        palette = get_named_palette(theme_key, variant_key)  # type: ignore[arg-type]
        updated["colors"] = palette_to_hex_dict(palette)
        updated["palette_source"] = {
            "type": "named",
            "theme": theme_key,
            "variant": variant_key,
        }
    elif isinstance(color_overrides, dict) and color_overrides:
        base_colors: dict[str, str] = {}
        existing = updated.get("colors")
        if isinstance(existing, dict):
            parsed = _parse_colors(existing)
            if parsed is not None:
                base_colors = parsed
        elif editor_job_context is not None and "colors" in editor_job_context:
            base_colors = copy.deepcopy(editor_job_context["colors"])
        if not base_colors:
            return {"ok": False, "errors": ["no base colors to patch — apply a named preset first"]}
        try:
            updated["colors"] = _merge_color_overrides(base_colors, color_overrides)
        except ValueError as exc:
            return {"ok": False, "errors": [str(exc)]}
        updated["palette_source"] = {"type": "custom"}
    else:
        return {
            "ok": False,
            "errors": ["specify theme+variant, use_editor_theme: true, or colors overrides"],
        }

    return {
        "ok": True,
        "graph": updated,
        "palette_source": updated.get("palette_source"),
    }
