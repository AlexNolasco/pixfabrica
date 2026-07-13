from __future__ import annotations

from typing import Any, ClassVar, Protocol, runtime_checkable

from pydantic import BaseModel


class PluginManifest(BaseModel):
    # Defaults to the PyPI package name if not set — collision-free by PyPI's guarantee.
    name: str
    display_name: str
    description: str
    requires_core: str  # PEP 440 specifier, e.g. ">=0.1.0,<1.0"
    license: str = "MIT"  # SPDX id — default for clips without clip_license override


@runtime_checkable
class PluginProtocol(Protocol):
    """Every Pixfabrica plugin must expose a manifest and its visual clip types."""

    manifest: ClassVar[PluginManifest]
    clip_types: ClassVar[list[type]]


def plugin_clip_types(plugin_class: type[Any]) -> list[type]:
    """Visual clip types from ``Plugin.clip_types``."""
    raw = getattr(plugin_class, "clip_types", None)
    return list(raw or [])
