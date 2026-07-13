"""Track-level GLEffect model and job helper tests."""

from __future__ import annotations

import pytest

from pixfabrica_core.composition.effect_def import (
    gl_effect_uv_margin,
    track_gl_overscan_fraction,
    validate_effect_chain,
)
from pixfabrica_core.composition.track import GLEffectTrack, SkiaTrack
from pixfabrica_core.job_effects import (
    chain_backend_for_track,
    track_needs_gl_effect_pipeline,
    tracks_need_gl_context,
)
from pixfabrica_std_effects.effects.float_gl import FloatGL
from pixfabrica_std_effects.effects.sway_gl import SwayGL


def test_skia_track_accepts_gl_effects() -> None:
    track = SkiaTrack(
        id="t1",
        effects=[
            FloatGL(id="fx1", enabled=True),
        ],
    )
    assert chain_backend_for_track(track) == "gl"


def test_track_effect_chain_rejects_too_many() -> None:
    with pytest.raises(ValueError, match="At most"):
        validate_effect_chain(
            [
                FloatGL(id="fx1", enabled=True),
                FloatGL(id="fx2", enabled=True),
                FloatGL(id="fx3", enabled=True),
                FloatGL(id="fx4", enabled=True),
            ]
        )


def test_gleffect_track_rejects_track_effects() -> None:
    with pytest.raises(ValueError, match="does not support track-level effects"):
        GLEffectTrack(
            id="post",
            effects=[FloatGL(id="fx1", enabled=True)],
            clips=[],
        )


def test_tracks_need_gl_for_skia_track_with_track_effects() -> None:
    track = SkiaTrack(
        id="t1",
        effects=[FloatGL(id="fx1", enabled=True)],
    )
    assert track_needs_gl_effect_pipeline(track, for_preview=True)
    assert tracks_need_gl_context([track], for_preview=True)


def test_idle_skia_track_without_effects_does_not_need_gl() -> None:
    track = SkiaTrack(id="t1")
    assert not track_needs_gl_effect_pipeline(track, for_preview=True)
    assert not tracks_need_gl_context([track], for_preview=True)


def test_track_gl_overscan_from_sway_tilt() -> None:
    fx = SwayGL(id="fx1", enabled=True, tilt=8.0)
    assert gl_effect_uv_margin(fx) >= 0.10
    track = SkiaTrack(id="t1", effects=[fx])
    assert track_gl_overscan_fraction(track.effects) >= 0.10


def test_track_gl_overscan_from_float_amplitude() -> None:
    fx = FloatGL(id="fx1", enabled=True, amplitude=0.12)
    assert gl_effect_uv_margin(fx) == pytest.approx(0.24)
