from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field, PrivateAttr, ValidationInfo, model_validator

from pixfabrica_core.composition.config import ThemeSetting, TypographySetting
from pixfabrica_core.composition.track import TrackClip
from pixfabrica_core.prepare_diagnostics import PrepareWarning
from pixfabrica_core.theme.color import ColorPalette
from pixfabrica_core.theme.palette_source import PaletteSource
from pixfabrica_core.theme.typography import FontPalette

if TYPE_CHECKING:
    from pixfabrica_core.audio.sound import SoundClip

CURRENT_SCHEMA_VERSION = 1


class RenderJob(BaseModel):
    schema_version: int = 1
    title: str
    author: str = ""
    description: str
    width: int = Field(default=1280, gt=0, le=3840)
    height: int = Field(default=720, gt=0, le=2160)
    fps: float = Field(default=24.0, gt=0, le=60.0)
    duration: float = Field(default=10.0, gt=0, le=3600.0)
    locale: str = "en"  # BCP 47 tag: "en", "es", "zh-CN"
    reference_height: int = Field(default=1080, gt=0)
    colors: ColorPalette = Field(default_factory=ColorPalette)
    palette_source: PaletteSource | None = None
    typography: FontPalette = Field(default_factory=FontPalette)
    theme: ThemeSetting | None = None
    typography_setting: TypographySetting | None = None
    # CRITICAL: default_factory prevents memory sharing
    tracks: list[TrackClip] = Field(default_factory=list)
    sounds: list[SoundClip] = Field(default_factory=list)
    parallelism: Literal["single", "multi"] = Field(
        default="single",
        description=(
            "Render strategy. 'single' uses the in-process serial loop. 'multi' spawns"
            " worker processes (cpu_count - 2, min 1) to compose frames in parallel,"
            " and auto-falls back to single for small jobs or when only 1 worker is"
            " available."
        ),
    )
    export_quality: Literal["draft", "standard", "master"] = Field(
        default="master",
        description="Export encode quality preset (pix_fmt, CRF/CQ, encoder preset).",
    )
    video_encoder: Literal["auto", "cpu", "nvenc"] = Field(
        default="auto",
        description=(
            "Video encoder backend. 'auto' prefers NVENC when FFmpeg exposes h264_nvenc,"
            " else CPU x264. 'nvenc' requires NVIDIA."
        ),
    )

    _variable_warnings: list[PrepareWarning] = PrivateAttr(default_factory=list)

    def project_variable_warnings(self) -> list[PrepareWarning]:
        return list(self._variable_warnings)

    @model_validator(mode="before")
    @classmethod
    def _deserialize_clips(cls, data: Any) -> Any:
        from pixfabrica_core.composition.registry import deserialize_setting

        if not isinstance(data, dict):
            return data

        if (raw_theme := data.get("theme")) and isinstance(raw_theme, dict):
            data = {**data, "theme": deserialize_setting(raw_theme)}

        if (raw_typo := data.get("typography_setting")) and isinstance(raw_typo, dict):
            data = {**data, "typography_setting": deserialize_setting(raw_typo)}

        if tracks := data.get("tracks"):
            from pixfabrica_core.composition.track import (
                GLEffectTrack,
                GLTrack,
                SkiaTrack,
                TrackClip,
            )

            _TRACK_TYPES: dict[str, type[TrackClip]] = {
                "std-skia-track": SkiaTrack,
                "std-gl-track": GLTrack,
                "std-post-track": GLEffectTrack,
            }
            resolved_tracks: list[Any] = []
            for track in tracks:
                if isinstance(track, dict):
                    from pixfabrica_core.composition.registry import deserialize_clip

                    clips = [
                        deserialize_clip(cl) if isinstance(cl, dict) else cl
                        for cl in track.get("clips", [])
                    ]
                    track_cls = _TRACK_TYPES.get(track.get("clip_type", ""), TrackClip)
                    resolved_tracks.append(track_cls.model_validate({**track, "clips": clips}))
                else:
                    resolved_tracks.append(track)
            data = {**data, "tracks": resolved_tracks}

        return data

    @model_validator(mode="after")
    def _resolve_timeline(self, info: ValidationInfo) -> RenderJob:
        # _resolve_timeline is destructive (it mutates clip.start in place
        # and re-scales typography). Re-running it on an already-resolved
        # payload would shift clip.start by an extra track.start and scale
        # typography twice. Workers ship the post-resolution model_dump and
        # set this context flag so re-validation is a no-op.
        if info.context and info.context.get("skip_resolve_timeline"):
            return self
        for track in self.tracks:
            if track.duration is None:
                track.duration = self.duration
            for clip in track.clips:
                if clip.duration is None:
                    clip.duration = track.duration
                clip.start = track.start + clip.start
        for sound in self.sounds:
            if sound.duration is None:
                sound.duration = self.duration
        scale = self.height / self.reference_height
        object.__setattr__(self, "typography", self.typography.scale(scale))
        return self

    @model_validator(mode="after")
    def _apply_project_variables(self, info: ValidationInfo) -> RenderJob:
        from pixfabrica_core.project_variables import apply_project_variables

        self._variable_warnings = apply_project_variables(self)
        return self
