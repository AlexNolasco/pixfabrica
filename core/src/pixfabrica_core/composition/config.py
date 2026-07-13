"""Job-level project settings.

These run once during the prepare phase (before the render loop) and produce
values — ColorPalette, FontPalette — that are baked into JobInfo before any
visual clip sees the context.

Concrete implementations live in plugins (e.g. pixfabrica-std).
"""

from __future__ import annotations

import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel

from pixfabrica_core.theme.color import ColorPalette
from pixfabrica_core.theme.typography import FontPalette


@dataclass(frozen=True, slots=True)
class ThemeContext:
    """Minimal context passed to ProjectSetting.resolve().

    Deliberately excludes ColorPalette / FontPalette — those are what
    project settings produce, not what they consume.
    """

    width: int
    height: int
    temp_dir: Path
    cache_dir: Path = field(
        default_factory=lambda: Path(tempfile.gettempdir()) / "pixfabrica_cache"
    )
    cancel: threading.Event | None = None


class ProjectSetting(BaseModel):
    """Abstract base for settings that run once at job startup, not per frame."""

    setting_type: ClassVar[str] = ""
    id: str
    enabled: bool = True


class ThemeSetting(ProjectSetting):
    """Produces a ColorPalette. Subclass in plugins to provide concrete strategies."""

    async def resolve(self, ctx: ThemeContext) -> ColorPalette:
        raise NotImplementedError(f"{self.__class__.__name__} must implement resolve()")


class TypographySetting(ProjectSetting):
    """Produces a FontPalette. Subclass in plugins to provide concrete strategies."""

    async def resolve(self, ctx: ThemeContext) -> FontPalette:
        raise NotImplementedError(f"{self.__class__.__name__} must implement resolve()")
