"""Compose agent tool definitions and handlers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pixfabrica_api.compose_catalog import (
    get_clip_detail_for_compose,
    list_catalog_clips_for_compose,
)
from pixfabrica_api.compose_graph import validate_graph_for_compose
from pixfabrica_api.compose_graph_builder import build_graph_from_spec
from pixfabrica_api.compose_theme import list_theme_presets_for_compose
from pixfabrica_api.compose_typography import list_typography_roles_for_compose

_BUILTIN_EXAMPLES: dict[str, str] = {
    "hello_world": "hello_world.json",
    "hello_world_transitions": "hello_world_transitions.json",
}

_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_catalog_clips",
            "description": (
                "List installed visual clip types with default params and track_kind (skia, gl, or post). "
                "Each clip must go on a track with the same track_kind — skia clips on skia tracks only, "
                "gl clips on gl tracks only."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "track_kind": {
                        "type": "string",
                        "enum": ["skia", "gl", "post"],
                        "description": "Optional filter: skia (2D/text), gl (GPU), post (effects)",
                    },
                    "category": {
                        "type": "string",
                        "description": "Optional category filter, e.g. text, background, video",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_clip_detail",
            "description": (
                "Get defaults, track_kind, and parameter summary for one clip_type before building."
                " track_kind must match the track you place the clip on."
            ),
            "parameters": {
                "type": "object",
                "required": ["clip_type"],
                "properties": {
                    "clip_type": {
                        "type": "string",
                        "description": "Catalog clip type, e.g. std-static-text",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "build_graph",
            "description": (
                "Build a project graph from a compact spec. Merges catalog defaults per clip."
                " track_kind on each track must match every clip's catalog track_kind"
                " (skia clips on skia tracks, gl on gl, post on post)."
                " Stagger track.start between scenes. One primary text per track; separate title/subtitle"
                " vertically (offset_y ~0.35 / ~0.65). Background before text in clips array."
                " Use typography_role (display_large hero, label_medium metadata)."
            ),
            "parameters": {
                "type": "object",
                "required": ["title", "tracks"],
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "duration": {"type": "number"},
                    "width": {"type": "integer"},
                    "height": {"type": "integer"},
                    "fps": {"type": "number"},
                    "tracks": {
                        "type": "array",
                        "description": (
                            "Each track: track_kind (skia|gl|post) + clips[{clip_type, params?, start?}]. "
                            "Clip track_kind from catalog must equal the track's track_kind."
                        ),
                        "items": {"type": "object"},
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "load_builtin_example",
            "description": (
                "Load a minimal Pixfabrica starter project JSON from built-in examples."
            ),
            "parameters": {
                "type": "object",
                "required": ["name"],
                "properties": {
                    "name": {
                        "type": "string",
                        "enum": sorted(_BUILTIN_EXAMPLES.keys()),
                        "description": "Built-in example id",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_typography_roles",
            "description": (
                "List typography_role values for text clips (display/title/body/label/mono). "
                "Use roles instead of inventing font sizes."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_theme_presets",
            "description": (
                "List named job color presets (theme + variant). "
                "Apply with apply_job_theme; prefer theme tokens on clips over raw hex."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "apply_job_theme",
            "description": (
                "Set job-level colors and palette_source on the current graph draft. "
                "Use theme+variant for a named preset, use_editor_theme to match the editor snapshot, "
                "or colors to patch individual tokens (switches to custom palette)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "theme": {
                        "type": "string",
                        "enum": [
                            "amber",
                            "violet",
                            "rose",
                            "emerald",
                            "slate",
                            "sky",
                            "gold",
                            "midnight",
                        ],
                    },
                    "variant": {"type": "string", "enum": ["dark", "light"]},
                    "use_editor_theme": {
                        "type": "boolean",
                        "description": "Copy colors/palette_source from editor_job_context on the request",
                    },
                    "colors": {
                        "type": "object",
                        "description": 'Partial token overrides, e.g. {"accent": "#ff00aa"}',
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "validate_graph",
            "description": (
                "Validate the current project graph. Call after build_graph or load_builtin_example;"
                " graph argument is optional when a draft was just built."
                " Returns warnings for overlapping text or stacked tracks — fix and re-validate."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "graph": {
                        "type": "object",
                        "description": (
                            "Optional web/render project JSON; omit to validate the last draft"
                        ),
                    }
                },
            },
        },
    },
]


def compose_tool_definitions() -> list[dict[str, Any]]:
    return [json.loads(json.dumps(tool)) for tool in _TOOL_DEFINITIONS]


def _examples_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "cli" / "examples"


def _load_builtin_example(name: str) -> dict[str, Any]:
    filename = _BUILTIN_EXAMPLES.get(name)
    if filename is None:
        known = ", ".join(sorted(_BUILTIN_EXAMPLES))
        raise ValueError(f"unknown example {name!r}; known: {known}")
    path = _examples_dir() / filename
    if not path.is_file():
        raise FileNotFoundError(f"builtin example not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"example {name!r} is not a JSON object")
    return data


def execute_compose_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Run a compose tool and return a JSON-serializable result payload."""
    if name == "list_catalog_clips":
        track_kind = arguments.get("track_kind")
        category = arguments.get("category")
        return list_catalog_clips_for_compose(
            track_kind=str(track_kind).strip() if track_kind else None,
            category=str(category).strip() if category else None,
        )

    if name == "get_clip_detail":
        clip_type = str(
            arguments.get("clip_type") or "",
        ).strip()
        if not clip_type:
            raise ValueError("clip_type is required")
        return get_clip_detail_for_compose(clip_type)

    if name == "build_graph":
        if not isinstance(arguments, dict):
            raise ValueError("build_graph spec must be an object")
        graph = build_graph_from_spec(arguments)
        return {"ok": True, "graph": graph}

    if name == "load_builtin_example":
        example_name = str(arguments.get("name", "")).strip()
        graph = _load_builtin_example(example_name)
        return {"ok": True, "name": example_name, "graph": graph}

    if name == "list_theme_presets":
        return list_theme_presets_for_compose()

    if name == "list_typography_roles":
        return list_typography_roles_for_compose()

    if name == "validate_graph":
        graph = arguments.get("graph")
        if not isinstance(graph, dict):
            raise ValueError("graph must be a JSON object")
        return validate_graph_for_compose(graph)

    raise ValueError(f"unknown compose tool: {name}")
