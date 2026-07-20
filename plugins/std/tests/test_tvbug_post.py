"""Tests for std-tvbug-post identity and bus intensity mapping."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pixfabrica_core.clips import ClipCategory, ClipTag, GLPostProcessClip
from pixfabrica_std import Plugin
from pixfabrica_std.effects.tvbug_post import (
    _BUS_INTENSITY_FLOOR,
    TvbugPost,
    bus_drive_intensity,
)


def test_clip_metadata_and_registration() -> None:
    assert TvbugPost.clip_type == "std-tvbug-post"
    assert TvbugPost.clip_category is ClipCategory.POSTPROCESS
    assert TvbugPost.clip_tags == [ClipTag.ANIMATED, ClipTag.GL]
    assert issubclass(TvbugPost, GLPostProcessClip)
    assert TvbugPost in Plugin.clip_types


def test_defaults_and_bus_fields() -> None:
    clip = TvbugPost(id="tvbug-post")
    assert clip.opacity == 1.0
    assert clip.frequency == 11.0
    assert clip.bus_select is None
    assert clip.sensitivity == 1.0
    assert "bus_select" in TvbugPost.model_fields
    assert "sensitivity" in TvbugPost.model_fields


def test_controls_are_bounded() -> None:
    with pytest.raises(ValidationError):
        TvbugPost(id="bad-opacity", opacity=-0.01)
    with pytest.raises(ValidationError):
        TvbugPost(id="bad-opacity-hi", opacity=1.01)
    with pytest.raises(ValidationError):
        TvbugPost(id="freq-low", frequency=3.5)
    with pytest.raises(ValidationError):
        TvbugPost(id="freq-high", frequency=24.5)


def test_no_bus_is_full_intensity() -> None:
    assert bus_drive_intensity(bus_selected=False, amplitude=0.0, sensitivity=1.0) == 1.0
    assert bus_drive_intensity(bus_selected=False, amplitude=1.0, sensitivity=8.0) == 1.0


def test_bus_silent_uses_floor() -> None:
    assert bus_drive_intensity(bus_selected=True, amplitude=0.0, sensitivity=1.0) == pytest.approx(
        _BUS_INTENSITY_FLOOR
    )


def test_bus_loud_reaches_full() -> None:
    assert bus_drive_intensity(bus_selected=True, amplitude=1.0, sensitivity=1.0) == pytest.approx(
        1.0
    )


def test_bus_mid_amplitude_mixes_floor_to_one() -> None:
    mid = bus_drive_intensity(bus_selected=True, amplitude=0.5, sensitivity=1.0)
    assert mid == pytest.approx(_BUS_INTENSITY_FLOOR + 0.5 * (1.0 - _BUS_INTENSITY_FLOOR))


def test_sensitivity_scales_drive() -> None:
    soft = bus_drive_intensity(bus_selected=True, amplitude=0.25, sensitivity=1.0)
    hot = bus_drive_intensity(bus_selected=True, amplitude=0.25, sensitivity=4.0)
    assert hot > soft
    assert hot == pytest.approx(1.0)
