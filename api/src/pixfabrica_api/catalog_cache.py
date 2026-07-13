"""In-memory plugin catalog built at API startup and rebuilt on refresh."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from pixfabrica_api.plugin_registry import register_discovered_plugins
from pixfabrica_core.catalog import CatalogCache, build_catalog_cache

_CONFIG_PATH = Path(__file__).parent.parent.parent.parent.parent / "pixfabrica.toml"

_catalog_cache: CatalogCache = CatalogCache(clips=(), details={})


def _load_config() -> dict[str, Any]:
    if not _CONFIG_PATH.exists():
        return {}
    with open(_CONFIG_PATH, "rb") as f:
        return tomllib.load(f)


def _plugin_config_sets() -> tuple[set[str], set[str]]:
    config = _load_config()
    plugins_cfg = config.get("plugins", {})
    disabled = set(plugins_cfg.get("disabled", []))
    pinned = set(plugins_cfg.get("pinned", []))
    return disabled, pinned


def rebuild_catalog_cache() -> CatalogCache:
    global _catalog_cache
    disabled, pinned = _plugin_config_sets()
    discovered, _failed = register_discovered_plugins()
    _catalog_cache = build_catalog_cache(
        discovered,
        disabled_plugin_ids=disabled,
        pinned_plugin_ids=pinned,
    )
    return _catalog_cache


def get_catalog_cache() -> CatalogCache:
    return _catalog_cache
