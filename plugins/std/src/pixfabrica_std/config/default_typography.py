"""DefaultTypography — standard type scale with configurable font families."""

from __future__ import annotations

from typing import ClassVar

from pydantic import Field

from pixfabrica_core.clips import ClipCategory
from pixfabrica_core.composition.config import ThemeContext, TypographySetting
from pixfabrica_core.theme.typography import FontPalette

_MONO_ROLES: frozenset[str] = frozenset({"mono_large", "mono_medium", "mono_small"})


class DefaultTypography(TypographySetting):
    """Standard type scale with configurable font families.

    All 15 roles use ``family``; the three monospace roles use ``mono_family``
    instead.  Sizes and weights come from the built-in scale — swap a
    dedicated TypographySetting plugin when you need a fully custom scale.
    """

    setting_type: ClassVar[str] = "std-default-typography"
    clip_category: ClassVar[ClipCategory] = ClipCategory.THEME_GENERATOR

    family: str = Field(
        default="Inter",
        description="Font family applied to all non-monospace roles.",
    )
    mono_family: str = Field(
        default="JetBrains Mono",
        description="Font family applied to mono_large, mono_medium, and mono_small.",
    )

    async def resolve(self, ctx: ThemeContext) -> FontPalette:
        base = FontPalette()
        updates: dict = {}
        for role in FontPalette.model_fields:
            spec = getattr(base, role)
            target = self.mono_family if role in _MONO_ROLES else self.family
            if spec.family != target:
                updates[role] = spec.model_copy(update={"family": target})
        return base.model_copy(update=updates) if updates else base
