from __future__ import annotations

from typing import ClassVar

from pixfabrica_core.clips import ClipCategory, ClipGL, ClipSkia, PrepareContext, RenderContext
from pixfabrica_core.graphics import Rect


class SpacerSkia(ClipSkia):
    """Reserves a layout band without drawing anything."""

    clip_type: ClassVar[str] = "std-spacer-skia"
    clip_category: ClassVar[ClipCategory] = ClipCategory.UTILITY

    async def prepare(self, _ctx: PrepareContext, _bounds: Rect | None = None) -> None:
        pass

    def draw(self, _ctx: RenderContext) -> None:
        pass


class SpacerGL(ClipGL):
    """Reserves a layout band without drawing anything."""

    clip_type: ClassVar[str] = "std-spacer-gl"
    clip_category: ClassVar[ClipCategory] = ClipCategory.UTILITY

    async def prepare(self, _ctx: PrepareContext, _bounds: Rect | None = None) -> None:
        pass

    def draw(self, _ctx: RenderContext) -> None:
        pass
