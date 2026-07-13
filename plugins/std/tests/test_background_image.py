"""Tests for std-background-image motion offsets and bus drift smoothing."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from pixfabrica_core.audio.bus import AudioBusFrame
from pixfabrica_core.clips import JobInfo, PrepareContext, RenderContext, TimeState
from pixfabrica_core.graphics import Rect
from pixfabrica_core.theme.color import ColorPalette
from pixfabrica_core.theme.typography import FontPalette
from pixfabrica_std.common import FitMode
from pixfabrica_std.image.background_image import (
    _COVER_BOOST,
    _MOTION_AMOUNT_RATIO,
    BackgroundImage,
)


def _bounds() -> Rect:
    return Rect(0, 0, 1000, 500)


def _ctx(*, t: float = 0.0, frame: int = 0, start: float = 0.0) -> RenderContext:
    job = JobInfo(
        title="t",
        description="d",
        width=1000,
        height=500,
        fps=30.0,
        duration=10.0,
        colors=ColorPalette(),
        typography=FontPalette(),
        locale="en",
    )
    return RenderContext(
        job=job,
        time=TimeState(frame=frame, t=t),
        bounds=_bounds(),
        canvas=MagicMock(),
    )


def _clip(**kwargs) -> BackgroundImage:
    return BackgroundImage(id="bg", **kwargs)


def test_circular_motion_starts_on_x_axis() -> None:
    clip = _clip(motion="circular", motion_speed=20.0)
    dx, dy = clip._motion_offset(_ctx(t=0.0), _bounds())
    amount = _MOTION_AMOUNT_RATIO * 500.0
    assert dx == pytest.approx(amount)
    assert dy == pytest.approx(0.0)


def test_motion_uses_clip_local_time() -> None:
    clip = _clip(motion="circular", motion_speed=20.0, start=5.0)
    at_global = clip._motion_offset(_ctx(t=5.0), _bounds())
    at_zero = clip._motion_offset(_ctx(t=0.0), _bounds())
    assert at_global == pytest.approx(at_zero)


def test_infinity_motion_is_zero_at_phase_zero() -> None:
    clip = _clip(motion="infinity", motion_speed=20.0)
    dx, dy = clip._motion_offset(_ctx(t=0.0), _bounds())
    assert dx == pytest.approx(0.0)
    assert dy == pytest.approx(0.0)


def test_infinity_motion_reaches_horizontal_extremes() -> None:
    clip = _clip(motion="infinity", motion_speed=40.0)
    amount = _MOTION_AMOUNT_RATIO * 500.0
    quarter = clip._motion_offset(_ctx(t=10.0), _bounds())
    assert quarter[0] == pytest.approx(amount, rel=1e-3)


def test_bus_drift_maps_smoothed_bass_and_mid() -> None:
    clip = _clip(motion="bus_drift")
    clip._bus_drift_active = True  # noqa: SLF001
    clip._smoothed_bass = np.asarray([1.0, 0.0], dtype=np.float32)  # noqa: SLF001
    clip._smoothed_mid = np.asarray([0.0, 1.0], dtype=np.float32)  # noqa: SLF001
    amount = _MOTION_AMOUNT_RATIO * 500.0

    dx0, dy0 = clip._motion_offset(_ctx(t=0.0, frame=0), _bounds())
    assert dx0 == pytest.approx(amount)
    assert dy0 == pytest.approx(-amount)

    dx1, dy1 = clip._motion_offset(_ctx(t=1.0 / 30.0, frame=1), _bounds())
    assert dx1 == pytest.approx(-amount)
    assert dy1 == pytest.approx(amount)


def test_bus_drift_without_bus_falls_back_to_circular() -> None:
    clip = _clip(motion="bus_drift", motion_speed=20.0)
    circular = _clip(motion="circular", motion_speed=20.0)
    assert clip._motion_offset(_ctx(t=3.0), _bounds()) == pytest.approx(  # noqa: SLF001
        circular._motion_offset(_ctx(t=3.0), _bounds())
    )


def test_bus_drift_timeline_uses_job_wide_normalization(tmp_path: Path) -> None:
    import asyncio

    clip = _clip(motion="bus_drift", bus_select="main")
    frames = [
        AudioBusFrame(
            spectrum=[0.0] * 64,
            bass=0.01,
            mid=0.02,
            high=0.0,
            beat=False,
            amplitude=0.0,
        ),
        AudioBusFrame(
            spectrum=[0.0] * 64,
            bass=0.9,
            mid=0.7,
            high=0.0,
            beat=False,
            amplitude=0.0,
        ),
    ]
    ji = JobInfo(
        title="t",
        description="d",
        width=1000,
        height=500,
        fps=30.0,
        duration=2 / 30.0,
        colors=ColorPalette(),
        typography=FontPalette(),
        locale="en",
    )
    td = tmp_path / "temp"
    cd = tmp_path / "cache"
    td.mkdir()
    cd.mkdir()
    ctx = PrepareContext(job=ji, temp_dir=td, cache_dir=cd, audio={"main": frames})
    asyncio.run(clip.prepare(ctx))
    assert clip._bus_drift_active is True  # noqa: SLF001
    bass = clip._smoothed_bass  # noqa: SLF001
    mid = clip._smoothed_mid  # noqa: SLF001
    assert bass[1] > bass[0]
    assert mid[1] > mid[0]
    assert bass[1] > 0.5


def test_zoom_disabled_when_motion_active() -> None:
    clip = _clip(motion="circular", sensitivity=0.5)
    clip._image = MagicMock()  # noqa: SLF001
    ctx = _ctx()
    ctx = ctx.model_copy(
        update={"audio_bus_frame": AudioBusFrame.zero().model_copy(update={"bass": 1.0})}
    )
    clip.draw(ctx)
    ctx.canvas.scale.assert_called_once_with(1.0, 1.0)


def test_cover_scale_multiplies_cover_draw_size() -> None:
    from pixfabrica_std.image.background_image import _draw_fitted

    image = MagicMock()
    image.width.return_value = 1000
    image.height.return_value = 1000
    canvas = MagicMock()
    bounds = Rect(0, 0, 1000, 1000)
    paint = MagicMock()

    _draw_fitted(canvas, bounds, image, FitMode.COVER, paint, cover_boost=1.0)
    plain = canvas.drawImageRect.call_args.args[2].width()
    canvas.reset_mock()
    _draw_fitted(canvas, bounds, image, FitMode.COVER, paint, cover_boost=1.1)
    scaled = canvas.drawImageRect.call_args.args[2].width()
    assert scaled == pytest.approx(plain * 1.1)


def test_draw_skips_clip_when_overscan_active() -> None:
    image = MagicMock()
    image.width.return_value = 1000
    image.height.return_value = 1000
    canvas = MagicMock()
    ctx = _ctx().model_copy(update={"canvas": canvas, "overscan": 0.08})

    clip = _clip(cover_scale=1.0, motion="none")
    clip._image = image  # noqa: SLF001
    clip.draw(ctx)
    canvas.clipRect.assert_not_called()


def test_draw_applies_cover_scale_and_motion_boost() -> None:
    image = MagicMock()
    image.width.return_value = 1000
    image.height.return_value = 1000
    canvas = MagicMock()
    ctx = _ctx().model_copy(update={"canvas": canvas})

    clip = _clip(cover_scale=1.1, motion="none")
    clip._image = image  # noqa: SLF001
    clip.draw(ctx)
    scaled_only = canvas.drawImageRect.call_args.args[2].width()

    canvas.reset_mock()
    clip = _clip(cover_scale=1.1, motion="circular")
    clip._image = image  # noqa: SLF001
    clip.draw(ctx)
    with_motion = canvas.drawImageRect.call_args.args[2].width()

    assert with_motion == pytest.approx(scaled_only * _COVER_BOOST)
