"""Plugin discovery endpoint.

GET  /plugins          — list all plugins with their clip types and schema
PATCH /plugins/{id}/disabled — toggle a plugin's disabled state
PATCH /plugins/{id}/pinned   — toggle a plugin's pinned state
"""

from __future__ import annotations

import hashlib
import json
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from pixfabrica_api.catalog_cache import rebuild_catalog_cache
from pixfabrica_core.catalog import catalog_entry_for_clip_class
from pixfabrica_core.plugins.discovery import discover_plugins

router = APIRouter(prefix="/plugins", tags=["plugins"])

# Path to pixfabrica.toml at repo root (two levels up from this file)
_CONFIG_PATH = Path(__file__).parent.parent.parent.parent.parent / "pixfabrica.toml"


def _load_config() -> dict[str, Any]:
    if not _CONFIG_PATH.exists():
        return {}
    with open(_CONFIG_PATH, "rb") as f:
        return tomllib.load(f)


def _save_config(config: dict[str, Any]) -> None:
    """Write back pixfabrica.toml using a minimal TOML serialiser (no extra deps)."""
    import re

    lines: list[str] = []
    for section, value in config.items():
        lines.append(f"[{section}]")
        if isinstance(value, dict):
            for k, v in value.items():
                if isinstance(v, list):
                    items = ", ".join(f'"{x}"' for x in v)
                    lines.append(f"{k} = [{items}]")
                elif isinstance(v, bool):
                    lines.append(f"{k} = {'true' if v else 'false'}")
                elif isinstance(v, (int, float)):
                    lines.append(f"{k} = {v}")
                else:
                    escaped = re.sub(r'([\\"])', r"\\\1", str(v))
                    lines.append(f'{k} = "{escaped}"')
        lines.append("")
    _CONFIG_PATH.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ClipTypeInfo(BaseModel):
    clip_type: str
    category: str
    tags: list[str]
    description: str
    icon: str
    parameters: dict[str, Any]  # JSON Schema from Pydantic model_json_schema()


class PluginInfo(BaseModel):
    id: str  # package name, e.g. "pixfabrica-std"
    version: str
    author: str | None
    disabled: bool
    pinned: bool
    clip_types: list[ClipTypeInfo]


class PatchDisabled(BaseModel):
    disabled: bool


class PatchPinned(BaseModel):
    pinned: bool


class RefreshPluginsResponse(BaseModel):
    refresh_id: str
    changed_plugin_ids: list[str]
    plugins: list[PluginInfo]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
_LAST_REFRESH_SNAPSHOT: dict[str, str] = {}


def _snapshot_plugins(plugins: list[PluginInfo]) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for plugin in plugins:
        payload = {
            "version": plugin.version,
            "disabled": plugin.disabled,
            "pinned": plugin.pinned,
            "clip_types": sorted(n.clip_type for n in plugin.clip_types),
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        snapshot[plugin.id] = digest
    return snapshot


@router.get("", response_model=list[PluginInfo])
async def list_plugins() -> list[PluginInfo]:
    config = _load_config()
    disabled_set: set[str] = set(config.get("plugins", {}).get("disabled", []))
    pinned_set: set[str] = set(config.get("plugins", {}).get("pinned", []))

    discovered, _failed = discover_plugins()

    result: list[PluginInfo] = []
    for plugin in discovered:
        clip_types: list[ClipTypeInfo] = []
        for clip_cls in plugin.clip_types:
            entry = catalog_entry_for_clip_class(clip_cls)
            if entry is None:
                continue
            clip_types.append(
                ClipTypeInfo(
                    clip_type=entry.clip_type,
                    category=entry.category,
                    tags=entry.tags,
                    description=entry.description,
                    icon=entry.icon,
                    parameters=entry.parameters,
                )
            )
        result.append(
            PluginInfo(
                id=plugin.package_name,
                version=plugin.version,
                author=plugin.author,
                disabled=plugin.package_name in disabled_set,
                pinned=plugin.package_name in pinned_set,
                clip_types=clip_types,
            )
        )
    return result


@router.post("/refresh", response_model=RefreshPluginsResponse)
async def refresh_plugins() -> RefreshPluginsResponse:
    global _LAST_REFRESH_SNAPSHOT

    rebuild_catalog_cache()
    plugins = await list_plugins()
    current_snapshot = _snapshot_plugins(plugins)
    changed_plugin_ids = sorted(
        {
            plugin_id
            for plugin_id in set(_LAST_REFRESH_SNAPSHOT) | set(current_snapshot)
            if _LAST_REFRESH_SNAPSHOT.get(plugin_id) != current_snapshot.get(plugin_id)
        }
    )
    _LAST_REFRESH_SNAPSHOT = current_snapshot

    refresh_id = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    return RefreshPluginsResponse(
        refresh_id=refresh_id,
        changed_plugin_ids=changed_plugin_ids,
        plugins=plugins,
    )


@router.patch("/{plugin_id}/disabled", response_model=PluginInfo)
async def set_disabled(plugin_id: str, body: PatchDisabled) -> PluginInfo:
    config = _load_config()
    plugins_cfg = config.setdefault("plugins", {})
    disabled: list[str] = plugins_cfg.get("disabled", [])

    if body.disabled and plugin_id not in disabled:
        disabled.append(plugin_id)
    elif not body.disabled and plugin_id in disabled:
        disabled.remove(plugin_id)
    plugins_cfg["disabled"] = disabled
    _save_config(config)
    rebuild_catalog_cache()

    # Return updated info
    plugins = await list_plugins()
    match = next((p for p in plugins if p.id == plugin_id), None)
    if match is None:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")
    return match


@router.patch("/{plugin_id}/pinned", response_model=PluginInfo)
async def set_pinned(plugin_id: str, body: PatchPinned) -> PluginInfo:
    config = _load_config()
    plugins_cfg = config.setdefault("plugins", {})
    pinned: list[str] = plugins_cfg.get("pinned", [])

    if body.pinned and plugin_id not in pinned:
        pinned.append(plugin_id)
    elif not body.pinned and plugin_id in pinned:
        pinned.remove(plugin_id)
    plugins_cfg["pinned"] = pinned
    _save_config(config)
    rebuild_catalog_cache()

    plugins = await list_plugins()
    match = next((p for p in plugins if p.id == plugin_id), None)
    if match is None:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_id}' not found")
    return match
