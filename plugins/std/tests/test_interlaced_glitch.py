"""Tests for the bus-free interlaced glitch post-processing effect."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pixfabrica_core.clips import ClipCategory, ClipTag, GLPostProcessClip
from pixfabrica_std import Plugin
from pixfabrica_std.effects.interlaced_glitch import InterlacedGlitch


def test_clip_metadata_and_registration() -> None:
    assert InterlacedGlitch.clip_type == "std-interlaced-glitch"
    assert InterlacedGlitch.clip_category is ClipCategory.POSTPROCESS
    assert InterlacedGlitch.clip_tags == [ClipTag.ANIMATED, ClipTag.GL]
    assert InterlacedGlitch.clip_license == "CC-BY-NC-SA-3.0"
    assert issubclass(InterlacedGlitch, GLPostProcessClip)
    assert InterlacedGlitch in Plugin.clip_types


def test_source_faithful_defaults_and_bus_free_contract() -> None:
    clip = InterlacedGlitch(id="interlaced-glitch")

    assert clip.speed == 1.0
    assert clip.directions == 16
    assert clip.samples == 10
    assert clip.directions * clip.samples == 160
    assert clip.opacity == 1.0
    assert "bus_select" not in InterlacedGlitch.model_fields
    assert "sensitivity" not in InterlacedGlitch.model_fields
    assert "strength" not in InterlacedGlitch.model_fields
    assert "smear" not in InterlacedGlitch.model_fields
    assert "rgb_split" not in InterlacedGlitch.model_fields
    assert "interlace" not in InterlacedGlitch.model_fields
    assert "seed" not in InterlacedGlitch.model_fields


def test_controls_are_bounded() -> None:
    with pytest.raises(ValidationError):
        InterlacedGlitch(id="transparent", opacity=-0.1)
    with pytest.raises(ValidationError):
        InterlacedGlitch(id="opaque", opacity=1.1)
    with pytest.raises(ValidationError):
        InterlacedGlitch(id="too-few-directions", directions=2)
    with pytest.raises(ValidationError):
        InterlacedGlitch(id="too-many-samples", samples=11)
    with pytest.raises(ValidationError):
        InterlacedGlitch(id="too-fast", speed=3.1)


def test_lowest_quality_reduces_sampling_work_twentyfold() -> None:
    clip = InterlacedGlitch(id="fast", directions=4, samples=2)

    assert clip.directions * clip.samples == 8
