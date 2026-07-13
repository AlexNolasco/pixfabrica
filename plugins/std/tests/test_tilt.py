"""Tests for shared band tilt helpers."""

from __future__ import annotations

import math

from pixfabrica_std.tilt import (
    ANGLE_BAND_SKEW_MAX,
    ANGLE_BAND_SKEW_MIN,
    band_left_center_y,
    band_skew_px,
)


def test_band_skew_limits_avoid_tan_singularity():
    assert ANGLE_BAND_SKEW_MIN == -89.0
    assert ANGLE_BAND_SKEW_MAX == 89.0


def test_band_skew_px_sign_matches_skia_convention():
    w = 1000.0
    assert band_skew_px(w, 0.0) == 0.0
    assert math.isclose(band_skew_px(w, 45.0), w)
    assert math.isclose(band_skew_px(w, -45.0), -w)


def test_band_left_center_y_places_mid_frame_center_at_offset():
    w, h = 1920.0, 1080.0
    offset_y = 0.5

    for angle in (0.0, 5.0, 15.0, 45.0, -45.0):
        skew = band_skew_px(w, -angle)
        left_center = band_left_center_y(h, offset_y, skew)
        mid_center = left_center - (skew / w) * (w / 2.0)
        assert math.isclose(mid_center, offset_y * h)
