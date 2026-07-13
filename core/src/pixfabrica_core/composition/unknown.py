"""Placeholder clips for unknown or unregistered clip types.

These are returned by the registry deserializers when a clip_type is not
found. They preserve the original payload so jobs round-trip losslessly,
and are no-ops at render time.
"""

from __future__ import annotations

from typing import Any, ClassVar

from pixfabrica_core.clips.base import Clip, ClipCategory, PrepareContext
from pixfabrica_core.composition.config import ProjectSetting
from pixfabrica_core.composition.effect_def import EffectContext, EffectInstance


class UnknownClip(Clip):
    """Placeholder for visual clips whose clip_type is not in the registry."""

    clip_type: ClassVar[str] = "__unknown__"
    clip_category: ClassVar[ClipCategory] = ClipCategory.UTILITY

    raw_clip_type: str = ""
    raw_data: dict[str, Any] = {}

    async def prepare(self, _ctx: PrepareContext, _bounds: Any = None) -> None:
        pass


class UnknownEffect(EffectInstance):
    """Placeholder for effect plugins whose effect_type is not in the registry."""

    effect_type: ClassVar[str] = "__unknown_effect__"

    raw_effect_type: str = ""
    raw_data: dict[str, Any] = {}

    async def prepare(self, _ctx: PrepareContext, _bounds: Any = None) -> None:
        pass

    def apply(self, _ctx: EffectContext) -> None:
        pass


class UnknownProjectSetting(ProjectSetting):
    """Placeholder for project settings whose setting_type is not in the registry."""

    setting_type: ClassVar[str] = "__unknown_config__"

    raw_setting_type: str = ""
    raw_data: dict[str, Any] = {}
