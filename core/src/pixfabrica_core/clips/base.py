from __future__ import annotations

import os
import tempfile
import threading
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, TypedDict

from pydantic import BaseModel

from pixfabrica_core.audio.timeline_store import TimelineMemoryStore
from pixfabrica_core.prepare_diagnostics import PrepareDiagnostics
from pixfabrica_core.theme.color import ColorPalette
from pixfabrica_core.theme.typography import FontPalette

if TYPE_CHECKING:
    from pixfabrica_core.audio.bus import AudioTimeline
    from pixfabrica_core.graphics import Rect


class ClipCategory(StrEnum):
    BACKGROUND = "background"
    TEXT = "text"
    EFFECTS = "effects"
    PARTICLES = "particles"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    UTILITY = "utility"
    TRACK = "track"
    THEME_GENERATOR = "theme_generator"
    MATH = "math"
    LOGIC = "logic"
    PROGRESS = "progress"
    LYRICS = "lyrics"
    POSTPROCESS = "postprocess"
    MESH = "mesh"
    PLAYER = "player"
    # ... more to come as we analyze existing plugins and identify common features


class ClipTag(StrEnum):
    """Opaque i18n keys — never displayed raw. UI resolves via locale table or plugin manifest."""

    ANIMATED = "animated"
    AUDIO_REACTIVE = "audio_reactive"
    GL = "gl"
    GLOW = "glow"
    GRADIENT = "gradient"
    LOOP = "loop"
    PARTICLE = "particle"
    SCROLLING = "scrolling"
    VIDEO = "video"
    LYRICS = "lyrics"
    # ... more to come as we analyze existing plugins and identify common features


class ClipPreset(TypedDict):
    id: str  # machine key — used as NLS suffix: preset.{clip_type}.{id}
    label: str  # English base string, seeded into schema.nls.json by gen-nls
    values: dict[str, Any]  # sparse: only the fields this preset overrides


class Clip(BaseModel):
    """Placed timeline instance base. Plugin authors subclass VisualClip / ClipSkia / ClipGL."""

    clip_type: ClassVar[str] = ""
    clip_category: ClassVar[ClipCategory] = ClipCategory.UTILITY
    clip_tags: ClassVar[list[str]] = []
    # SPDX license id; empty string inherits PluginManifest.license for catalog indexing.
    clip_license: ClassVar[str] = ""

    id: str  # system-assigned, unique within a render job
    start: float = 0.0
    duration: float | None = None
    enabled: bool = True

    async def prepare(self, _ctx: PrepareContext, _bounds: Rect | None = None) -> None:
        pass


@dataclass(frozen=True, slots=True)
class JobInfo:
    title: str
    description: str
    width: int  # render-surface width for this draw pass; use ctx.bounds in draw()
    height: int  # render-surface height for this draw pass
    fps: float
    duration: float
    colors: ColorPalette
    typography: FontPalette
    locale: str
    # Design/export dimensions from the project JSON. Zero means same as width/height.
    output_width: int = 0
    output_height: int = 0

    @property
    def design_width(self) -> int:
        return self.output_width if self.output_width > 0 else self.width

    @property
    def design_height(self) -> int:
        return self.output_height if self.output_height > 0 else self.height

    def scale_output_px(self, px: float) -> float:
        """Scale a pixel length or px/s value from design resolution to this render surface."""
        surface_h = max(1, self.height)
        design_h = max(1, self.design_height)
        return px * (surface_h / design_h)

    @property
    def total_frames(self) -> int:
        return round(self.duration * self.fps)


@dataclass(frozen=True, slots=True)
class PrepareContext:
    job: JobInfo
    temp_dir: Path
    cache_dir: Path = field(
        default_factory=lambda: Path(tempfile.gettempdir()) / "pixfabrica_cache"
    )
    cancel: threading.Event | None = None
    for_preview: bool = False
    # Resolved audio buses for the whole job, available at prepare() time so
    # audio-reactive clips can pre-compute per-frame state (smoothing,
    # running averages, beat histories, etc.) and keep draw() stateless.
    # Empty dict when the job has no sound clips.
    audio: AudioTimeline = field(default_factory=dict)
    diagnostics: PrepareDiagnostics | None = None
    timeline_store: TimelineMemoryStore | None = None
    # Set only while preparing per-clip effects — parent visual clip for bus inherit.
    parent_clip: Clip | None = None

    @classmethod
    def from_env(
        cls,
        job: JobInfo,
        *,
        cancel: threading.Event | None = None,
        audio: AudioTimeline | None = None,
        for_preview: bool = False,
        diagnostics: PrepareDiagnostics | None = None,
        timeline_store: TimelineMemoryStore | None = None,
    ) -> PrepareContext:
        _tmp = Path(tempfile.gettempdir())
        temp_dir = Path(os.environ.get("PIXFABRICA_TEMP_DIR", str(_tmp / "pixfabrica_temp")))
        cache_dir = Path(os.environ.get("PIXFABRICA_CACHE_DIR", str(_tmp / "pixfabrica_cache")))
        temp_dir.mkdir(parents=True, exist_ok=True)
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cls(
            job=job,
            temp_dir=temp_dir,
            cache_dir=cache_dir,
            cancel=cancel,
            audio=audio or {},
            for_preview=for_preview,
            diagnostics=diagnostics,
            timeline_store=timeline_store,
        )


@dataclass(frozen=True, slots=True)
class TimeState:
    frame: int
    t: float
    dt: float = 0.0
