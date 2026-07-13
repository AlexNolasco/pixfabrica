"""Tests for mesh spherical light direction helpers."""

from __future__ import annotations

import numpy as np
import pytest

from pixfabrica_std.mesh.shader_helper import (
    light_dir_in_eye_space,
    mesh_camera_view,
    spherical_unit_direction,
)


def test_spherical_unit_direction_defaults_to_below():
    assert spherical_unit_direction(0.0, -90.0) == pytest.approx((0.0, -1.0, 0.0), abs=1e-5)


def test_spherical_unit_direction_above():
    assert spherical_unit_direction(0.0, 90.0) == pytest.approx((0.0, 1.0, 0.0), abs=1e-5)


def test_light_dir_in_eye_space_matches_world_at_front_camera():
    view = mesh_camera_view(2.2, 0.0, 0.0)
    assert light_dir_in_eye_space(view, 0.0, -90.0) == pytest.approx((0.0, -1.0, 0.0), abs=1e-4)


def test_light_dir_transforms_with_camera_view():
    view_front = mesh_camera_view(2.2, 0.0, 0.0)
    view_side = mesh_camera_view(2.2, 90.0, 0.0)
    front = np.array(light_dir_in_eye_space(view_front, 90.0, 0.0))
    side = np.array(light_dir_in_eye_space(view_side, 90.0, 0.0))
    assert not np.allclose(front, side, atol=1e-3)
