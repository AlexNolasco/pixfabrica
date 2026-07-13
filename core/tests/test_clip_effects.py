"""Per-clip effects — model, registry, and job helpers."""

from __future__ import annotations

from typing import ClassVar

import pytest

from pixfabrica_core.clips import ClipCategory, RenderJob, VisualClip
from pixfabrica_core.composition.effect_def import (
    RasterEffect,
    validate_effect_chain,
)
from pixfabrica_core.composition.effect_registry import deserialize_effect, register_effect
from pixfabrica_core.composition.registry import deserialize_clip, register_clip_type
from pixfabrica_core.composition.track import FillLayout, SkiaTrack
from pixfabrica_core.job_effects import (
    job_requires_single_process,
    resolve_parallelism,
    tracks_need_gl_context,
)
from pixfabrica_std.background.solid_background import SolidBackground
from pixfabrica_std_effects.effects.blur_skia import BlurSkia
from pixfabrica_std_effects.effects.colorize_gl import ColorizeGL
from pixfabrica_std_effects.effects.invert_gl import InvertGL
from pixfabrica_std_effects.effects.saturation_gl import SaturationGL


class _SingletonRasterTestDouble(RasterEffect):
    """Inline singleton raster effect for job-gate tests (no heavy plugin deps)."""

    effect_type: ClassVar[str] = "test-singleton-raster-stub"
    clip_category: ClassVar[ClipCategory] = ClipCategory.EFFECTS
    singleton: ClassVar[bool] = True


def _register_std_effects() -> None:
    register_clip_type(SolidBackground)
    register_effect(BlurSkia)
    register_effect(ColorizeGL)
    register_effect(InvertGL)
    register_effect(SaturationGL)
    register_effect(_SingletonRasterTestDouble)


def test_validate_effect_chain_max_three() -> None:
    fx = BlurSkia(id="a", enabled=True)
    with pytest.raises(ValueError, match="At most 3"):
        validate_effect_chain([fx, fx, fx, fx])


def test_validate_effect_chain_homogeneous() -> None:
    with pytest.raises(ValueError, match="homogeneous"):
        validate_effect_chain(
            [
                BlurSkia(id="a", enabled=True),
                InvertGL(id="b", enabled=True),
            ]
        )


def test_deserialize_clip_with_effects() -> None:
    _register_std_effects()
    raw = {
        "clip_type": "std-solid-background",
        "id": "bg",
        "start": 0,
        "duration": 1,
        "effects": [
            {
                "effect_type": "std-blur-skia",
                "id": "fx1",
                "enabled": True,
                "radius": 2.0,
            }
        ],
    }
    el = deserialize_clip(raw)
    assert isinstance(el, VisualClip)
    assert len(el.effects) == 1
    assert el.effects[0].effect_type == "std-blur-skia"
    assert isinstance(el.effects[0], BlurSkia)
    assert el.effects[0].radius == 2.0


def test_job_without_effects_unchanged_parallelism() -> None:
    _register_std_effects()
    job = RenderJob.model_validate(
        {
            "title": "t",
            "description": "",
            "parallelism": "multi",
            "tracks": [
                {
                    "clip_type": "std-skia-track",
                    "id": "t1",
                    "start": 0,
                    "duration": 1,
                    "clips": [
                        {
                            "clip_type": "std-solid-background",
                            "id": "bg",
                            "start": 0,
                            "duration": None,
                        }
                    ],
                }
            ],
        }
    )
    assert job_requires_single_process(job) is False
    assert resolve_parallelism(job) == "multi"


def test_singleton_effect_forces_single_parallelism() -> None:
    _register_std_effects()
    job = RenderJob.model_validate(
        {
            "title": "t",
            "description": "",
            "parallelism": "multi",
            "tracks": [
                {
                    "clip_type": "std-skia-track",
                    "id": "t1",
                    "start": 0,
                    "duration": 1,
                    "clips": [
                        {
                            "clip_type": "std-solid-background",
                            "id": "bg",
                            "start": 0,
                            "duration": None,
                            "effects": [
                                {
                                    "effect_type": "test-singleton-raster-stub",
                                    "id": "ai",
                                    "enabled": True,
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    )
    assert job_requires_single_process(job) is True
    assert resolve_parallelism(job) == "single"


def test_skia_track_with_gl_effect_needs_gl_context() -> None:
    _register_std_effects()
    track = SkiaTrack(
        id="t1",
        start=0.0,
        duration=1.0,
        enabled=True,
        layout=FillLayout(),
        clips=[
            SolidBackground(
                id="bg",
                start=0.0,
                duration=1.0,
                effects=[
                    InvertGL(id="fx", enabled=True),
                ],
            )
        ],
    )
    assert tracks_need_gl_context([track], for_preview=True) is True


def test_deserialize_effect_round_trip() -> None:
    _register_std_effects()
    fx = deserialize_effect(
        {
            "effect_type": "std-invert-gl",
            "id": "inv",
            "enabled": True,
            "mix": 0.5,
        }
    )
    assert isinstance(fx, InvertGL)
    assert fx.mix == 0.5
