from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from pixfabrica_core.clips.base import ClipCategory


@dataclass(frozen=True, slots=True)
class ClipIconContext:
    clip_type: str
    category: str
    tags: list[str]


@runtime_checkable
class IconGenerator(Protocol):
    def svg(self, ctx: ClipIconContext) -> str: ...


class DefaultIconGenerator:
    def svg(self, ctx: ClipIconContext) -> str:
        from pixfabrica_core.composition.icons import CATEGORY_ICONS, FALLBACK_ICON

        try:
            category = ClipCategory(ctx.category)
        except ValueError:
            return FALLBACK_ICON
        return CATEGORY_ICONS.get(category, FALLBACK_ICON)


@dataclass(frozen=True, slots=True)
class StaticIconGenerator:
    svg_content: str

    def svg(self, ctx: ClipIconContext) -> str:
        return self.svg_content


_REGISTRY: dict[str, IconGenerator] = {}


def register_icon(clip_type: str, generator: IconGenerator) -> None:
    _REGISTRY[clip_type] = generator


def resolve_icon(ctx: ClipIconContext) -> str:
    generator = _REGISTRY.get(ctx.clip_type)
    if generator is not None:
        return generator.svg(ctx)
    return DefaultIconGenerator().svg(ctx)
