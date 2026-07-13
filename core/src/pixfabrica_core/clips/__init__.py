"""Canonical import path for visual clip types.

Plugin authors should import clip bases and render context from this package.
Job composition (``RenderJob``, tracks, effects, settings) lives under
``pixfabrica_core.composition``.
"""

from pixfabrica_core.clips.base import (
    Clip,
    ClipCategory,
    ClipPreset,
    ClipTag,
    JobInfo,
    PrepareContext,
    TimeState,
)
from pixfabrica_core.clips.visual import (
    ClipGL,
    ClipSkia,
    ClipTypeProtocol,
    DrawableProtocol,
    GLPostProcessClip,
    RenderContext,
    VisualClip,
)
from pixfabrica_core.composition.job import CURRENT_SCHEMA_VERSION, RenderJob

__all__ = [
    "Clip",
    "ClipGL",
    "ClipSkia",
    "ClipTypeProtocol",
    "CURRENT_SCHEMA_VERSION",
    "DrawableProtocol",
    "GLPostProcessClip",
    "JobInfo",
    "ClipCategory",
    "ClipPreset",
    "ClipTag",
    "PrepareContext",
    "RenderContext",
    "RenderJob",
    "TimeState",
    "VisualClip",
]
