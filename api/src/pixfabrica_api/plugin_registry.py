"""Register discovered plugin clip types for RenderJob deserialization."""

from __future__ import annotations

import logging
from typing import Any

from pixfabrica_core.composition.effect_registry import register_effect
from pixfabrica_core.composition.registry import register_clip_type, register_setting_type
from pixfabrica_core.plugins import plugin_clip_types
from pixfabrica_core.plugins.discovery import DiscoveredPlugin, FailedPlugin, discover_plugins

log = logging.getLogger("pixfabrica.api.plugins")


def _register_plugin_classes(plugin: type[Any]) -> int:
    count = 0
    for clip_cls in plugin_clip_types(plugin):
        register_clip_type(clip_cls)
        count += 1
    for cfg_cls in getattr(plugin, "project_settings", []) or []:
        register_setting_type(cfg_cls)
        count += 1
    for effect_cls in getattr(plugin, "effects", []) or []:
        register_effect(effect_cls)
        count += 1
    return count


def _register_installed_plugin_fallback(module_name: str, label: str) -> int:
    """Register a built-in plugin from its installed package when plugins/ scan misses."""
    try:
        module = __import__(module_name, fromlist=["Plugin"])
        plugin = module.Plugin
    except ImportError:
        return 0
    count = _register_plugin_classes(plugin)
    if count:
        log.info("registered %d clip type(s) from installed %s", count, label)
    return count


def _register_installed_std_fallback() -> int:
    return _register_installed_plugin_fallback("pixfabrica_std", "pixfabrica-std")


def _register_installed_std_effects_fallback() -> int:
    return _register_installed_plugin_fallback("pixfabrica_std_effects", "pixfabrica-std-effects")


def register_discovered_plugins(
    *,
    force: bool = False,
) -> tuple[list[DiscoveredPlugin], list[FailedPlugin]]:
    """Discover plugins and populate the global clip registries."""
    del force  # always refresh — registration is idempotent and cheap
    discovered, failed = discover_plugins()
    for f in failed:
        log.warning("plugin load failed: %s — %s", f.package_name, f.error)

    registered = 0
    for item in discovered:
        registered += _register_plugin_classes(item.plugin_class)

    if registered == 0:
        registered = _register_installed_std_fallback()
        registered += _register_installed_std_effects_fallback()
    elif registered:
        log.info("registered %d clip type(s) from %d plugin(s)", registered, len(discovered))

    return discovered, failed


def ensure_plugins_registered() -> None:
    """Call before deserializing RenderJob JSON in API workers."""
    register_discovered_plugins()
