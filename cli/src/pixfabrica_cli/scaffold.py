from __future__ import annotations

import re
from pathlib import Path

# Relative to plugins/<name>/ — Pixfabrica monorepo layout is required.
_CORE_PATH = "../../core"


def slug_to_package(name: str) -> str:
    """Convert a plugin slug to a valid Python package name. e.g. 'acme-rain' -> 'acme_rain'."""
    return re.sub(r"[-\s]+", "_", name).lower()


def slug_to_display(name: str) -> str:
    """Convert a plugin slug to a display name. e.g. 'acme-rain' -> 'Acme Rain'."""
    return " ".join(word.capitalize() for word in re.split(r"[-_\s]+", name))


def _pyproject_toml(name: str, package: str) -> str:
    return f"""\
[project]
name = "{name}"
version = "0.1.0"
requires-python = ">=3.12,<3.13"
description = ""
authors = []
dependencies = [
    "pixfabrica-core[audio]>=0.1.0,<1.0",
    "skia-python>=144.0.post2",
]

[tool.uv.sources]
pixfabrica-core = {{ path = "{_CORE_PATH}", editable = true }}

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/{package}"]
"""


def _readme_md(name: str, display: str) -> str:
    return f"""\
# {display}

Pixfabrica plugin **`{name}`**. Plugin development assumes a full [Pixfabrica](https://github.com/AlexNolasco/pixfabrica) checkout with this repo cloned under `plugins/{name}/` (so `pixfabrica-core` resolves via `../../core`).

## Install into Pixfabrica

From the **Pixfabrica repository root** (not this directory):

```bash
git clone https://github.com/AlexNolasco/{name}.git plugins/{name}
uv add --editable ./plugins/{name} --no-workspace
uv run pixfabrica plugin list --clip-types
```

That registers the plugin in the same `.venv` as `pixfabrica-core`, the API, CLI, and renderer. Restart the API dev server if it is already running.

## Develop the plugin

```bash
cd plugins/{name}
uv sync
uv run pytest   # after you add tests
```

`uv sync` here uses the path dependency on `../../core` and updates `uv.lock` in this repo. Commit `uv.lock` when you change dependencies.

## Layout

```
plugins/{name}/
├── pyproject.toml
├── uv.lock
└── src/
    └── {slug_to_package(name)}/
        ├── __init__.py
        ├── placeholder.py
        └── icons.py
```

Replace `placeholder.py` with your own clip types and register them on `Plugin.clip_types` in `__init__.py`.
"""


def _placeholder_clip_py(name: str) -> str:
    return f'''\
"""Placeholder Skia clip type — replace with your own implementation."""

from __future__ import annotations

from typing import ClassVar

import skia
from pydantic import Field

from pixfabrica_core.graphics import Rect
from pixfabrica_core.clips import ClipSkia, ClipCategory, PrepareContext, RenderContext


class PlaceholderRect(ClipSkia):
    """Filled rectangle placeholder for verifying plugin install and discovery."""

    clip_type: ClassVar[str] = "{name}-placeholder"
    clip_category: ClassVar[ClipCategory] = ClipCategory.UTILITY
    opacity: float = Field(default=0.85, ge=0.0, le=1.0)

    async def prepare(self, _ctx: PrepareContext, _bounds: Rect | None = None) -> None:
        pass

    def draw(self, ctx: RenderContext) -> None:
        canvas: skia.Canvas = ctx.canvas
        b = ctx.bounds
        paint = skia.Paint(AntiAlias=True)
        paint.setColor4f(skia.Color4f(0.9, 0.2, 0.6, self.opacity))
        inset_x = b.width * 0.1
        inset_y = b.height * 0.1
        canvas.drawRect(
            skia.Rect(
                b.x + inset_x,
                b.y + inset_y,
                b.x + b.width - inset_x,
                b.y + b.height - inset_y,
            ),
            paint,
        )
'''


def _init_py(name: str, display: str, package: str) -> str:
    return f"""\
from typing import ClassVar

from pixfabrica_core.plugins import PluginManifest

from {package} import icons as _icons  # noqa: F401 — register_icon side effects
from {package}.placeholder import PlaceholderRect


class Plugin:
    manifest: ClassVar[PluginManifest] = PluginManifest(
        name="{name}",
        display_name="{display}",
        description="Sample plugin — replace placeholder clip types with your own.",
        requires_core=">=0.1.0,<1.0",
    )
    clip_types: ClassVar[list[type]] = [PlaceholderRect]
"""


def scaffold_plugin(name: str, output_dir: Path) -> Path:
    """
    Scaffold a new Pixfabrica plugin package at output_dir/name.
    Returns the created plugin root directory.
    """
    package = slug_to_package(name)
    display = slug_to_display(name)
    plugin_dir = output_dir / name
    src_dir = plugin_dir / "src" / package

    src_dir.mkdir(parents=True, exist_ok=False)

    (plugin_dir / "pyproject.toml").write_text(_pyproject_toml(name, package), encoding="utf-8")
    (plugin_dir / "README.md").write_text(_readme_md(name, display), encoding="utf-8")
    (plugin_dir / ".gitignore").write_text(
        """\
.venv/
__pycache__/
*.py[cod]
.pytest_cache/
.ruff_cache/
dist/
*.egg-info/
""",
        encoding="utf-8",
    )

    (src_dir / "icons.py").write_text(
        """\
\"\"\"Optional icon overrides — register custom SVGs per clip_type.

Import is wired from __init__.py. Clip types without an entry here use the
category default from pixfabrica-core.
\"\"\"

# from pixfabrica_core.composition.icon_registry import StaticIconGenerator, register_icon
# register_icon("my-clip-type", StaticIconGenerator("<svg>...</svg>"))
""",
        encoding="utf-8",
    )

    (src_dir / "placeholder.py").write_text(_placeholder_clip_py(name), encoding="utf-8")
    (src_dir / "__init__.py").write_text(_init_py(name, display, package), encoding="utf-8")

    return plugin_dir
