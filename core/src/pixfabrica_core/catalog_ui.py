from __future__ import annotations

import contextlib
import json
from copy import deepcopy
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel


def load_plugin_ui_files(plugin_package_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    generated: dict[str, Any] = {}
    overrides: dict[str, Any] = {}

    gen_path = plugin_package_dir / "schema.ui.generated.json"
    if gen_path.is_file():
        with contextlib.suppress(json.JSONDecodeError, OSError):
            raw = json.loads(gen_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                generated = raw

    ovr_path = plugin_package_dir / "schema.ui.overrides.json"
    if ovr_path.is_file():
        with contextlib.suppress(json.JSONDecodeError, OSError):
            raw = json.loads(ovr_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                overrides = raw

    return generated, overrides


def deep_merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge override onto base; override wins at every overlapping key."""
    result = deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge_dict(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def merged_ui_spec_for_clip(
    generated: dict[str, Any],
    overrides: dict[str, Any],
    clip_type: str,
) -> dict[str, Any] | None:
    base = generated.get(clip_type)
    if not isinstance(base, dict):
        return None
    ovr = overrides.get(clip_type)
    if isinstance(ovr, dict) and ovr:
        return deep_merge_dict(base, ovr)
    return deepcopy(base)


def to_json_safe_catalog_value(value: Any) -> Any:
    """Convert a clip parameter default to a JSON-serializable catalog/API value."""
    from pixfabrica_core.theme.color import Color, ColorToken

    if isinstance(value, Color):
        return value.hex
    if isinstance(value, ColorToken):
        return value.value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, BaseModel):
        return {
            key: to_json_safe_catalog_value(item)
            for key, item in value.model_dump(mode="python").items()
        }
    if isinstance(value, dict):
        return {key: to_json_safe_catalog_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_json_safe_catalog_value(item) for item in value]
    return value


def find_non_json_serializable_default(
    defaults: dict[str, Any],
) -> tuple[str, Any, Exception] | None:
    """Return (field_name, value, error) for the first default that cannot be JSON-encoded."""
    for name, value in defaults.items():
        safe = to_json_safe_catalog_value(value)
        try:
            json.dumps(safe)
        except (TypeError, ValueError) as exc:
            return name, value, exc
    return None


def extract_defaults_from_json_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Extract property defaults from a Pydantic model_json_schema() document."""
    defaults: dict[str, Any] = {}
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return defaults
    for name, prop in properties.items():
        if not isinstance(prop, dict):
            continue
        if "default" in prop:
            defaults[name] = to_json_safe_catalog_value(prop["default"])
    return defaults


def parameters_schema_for_clip_class(clip_cls: type) -> dict[str, Any]:
    with contextlib.suppress(Exception):
        return clip_cls.model_json_schema()
    return {
        "type": "object",
        "title": getattr(clip_cls, "clip_type", ""),
    }


def extract_defaults_from_clip_class(clip_cls: type) -> dict[str, Any]:
    """Defaults from JSON Schema when possible, else from Pydantic model_fields."""
    with contextlib.suppress(Exception):
        defaults = extract_defaults_from_json_schema(clip_cls.model_json_schema())
        if defaults:
            return defaults

    from pydantic_core import PydanticUndefined

    defaults = {}
    for name, field in clip_cls.model_fields.items():
        if field.default is not PydanticUndefined:
            defaults[name] = to_json_safe_catalog_value(field.default)
        elif field.default_factory is not None:
            with contextlib.suppress(Exception):
                defaults[name] = to_json_safe_catalog_value(field.default_factory())
    return defaults
