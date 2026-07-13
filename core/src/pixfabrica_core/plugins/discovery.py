from __future__ import annotations

import importlib
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class DiscoveredPlugin:
    package_name: str
    version: str
    author: str | None
    plugin_class: type[Any]
    """Package directory containing schema.nls.json (e.g. .../pixfabrica_std)."""
    plugin_package_dir: Path

    @property
    def manifest(self):  # type: ignore[return]
        return getattr(self.plugin_class, "manifest", None)

    @property
    def clip_types(self) -> list[type]:
        from pixfabrica_core.plugins import plugin_clip_types

        return plugin_clip_types(self.plugin_class)

    @property
    def effects(self) -> list[type]:
        return list(getattr(self.plugin_class, "effects", []) or [])

    @property
    def project_settings(self) -> list[type]:
        return getattr(self.plugin_class, "project_settings", [])

    @property
    def job_asset_contributors(self) -> list[Any]:
        return getattr(self.plugin_class, "job_asset_contributors", [])


@dataclass
class FailedPlugin:
    package_name: str
    plugin_dir: str
    error: str


def discover_plugins(
    plugins_dir: Path | None = None,
) -> tuple[list[DiscoveredPlugin], list[FailedPlugin]]:
    """
    Scan plugins_dir for subdirectories containing a pyproject.toml.
    Each valid plugin exposes a Plugin class in its package __init__.py.
    Defaults to <repo-root>/plugins/ relative to this file.
    """
    if plugins_dir is None:
        plugins_dir = Path(__file__).parent.parent.parent.parent.parent / "plugins"

    discovered: list[DiscoveredPlugin] = []
    failed: list[FailedPlugin] = []

    if not plugins_dir.exists():
        return discovered, failed

    for toml_path in sorted(plugins_dir.glob("*/pyproject.toml")):
        plugin_dir = toml_path.parent

        try:
            with open(toml_path, "rb") as f:
                toml = tomllib.load(f)
        except Exception as exc:
            failed.append(
                FailedPlugin(
                    package_name="unknown",
                    plugin_dir=str(plugin_dir),
                    error=f"bad pyproject.toml: {exc}",
                )
            )
            continue

        project = toml.get("project", {})
        package_name = project.get("name", plugin_dir.name)
        version = project.get("version", "unknown")
        author = _parse_author(project)
        module_name = package_name.replace("-", "_")

        src_path = plugin_dir / "src"
        inject_path = src_path if src_path.exists() else plugin_dir
        package_dir_path = inject_path / module_name
        if str(inject_path) not in sys.path:
            sys.path.insert(0, str(inject_path))

        try:
            module = importlib.import_module(module_name)
            plugin_class = module.Plugin
        except Exception as exc:
            failed.append(
                FailedPlugin(package_name=package_name, plugin_dir=str(plugin_dir), error=str(exc))
            )
            continue

        discovered.append(
            DiscoveredPlugin(
                package_name=package_name,
                version=version,
                author=author,
                plugin_class=plugin_class,
                plugin_package_dir=package_dir_path,
            )
        )

    return discovered, failed


def _parse_author(project: dict) -> str | None:
    # PEP 621: authors = [{name = "...", email = "..."}]
    for entry in project.get("authors", []):
        if email := entry.get("email"):
            return email
        if name := entry.get("name"):
            return name
    return None
