"""Bus resolution helpers for per-clip effects."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import numpy as np
import pytest

from pixfabrica_core.audio.bus import AudioBusFrame
from pixfabrica_core.audio.mixin import AudioVisualMixin
from pixfabrica_core.clips import ClipSkia, JobInfo, PrepareContext, RenderContext, TimeState
from pixfabrica_core.composition.effect_def import (
    EffectContext,
    EffectInstance,
    effect_bus_active,
    effect_supports_bus,
    resolve_effect_bus_select,
)
from pixfabrica_core.graphics import Rect
from pixfabrica_core.theme.color import ColorPalette
from pixfabrica_core.theme.typography import FontPalette
from pixfabrica_std_effects.effects.blur_skia import BlurSkia


class _BusClip(AudioVisualMixin, ClipSkia):
    clip_type: ClassVar[str] = "test-bus-clip"

    async def prepare(self, _ctx, _bounds=None) -> None:
        pass

    def draw(self, _ctx: RenderContext) -> None:
        pass


class _StaticEffect(EffectInstance):
    effect_type: ClassVar[str] = "test-static-effect"

    def apply(self, _ctx) -> None:
        pass


def test_effect_supports_bus_only_when_schema_declares_it() -> None:
    assert effect_supports_bus(BlurSkia(id="fx")) is True
    assert effect_supports_bus(_StaticEffect(id="fx")) is False


def test_effect_bus_active_requires_positive_sensitivity() -> None:
    assert effect_bus_active(BlurSkia(id="fx", sensitivity=0.0)) is False
    assert effect_bus_active(BlurSkia(id="fx", sensitivity=0.2)) is True


def test_resolve_effect_bus_select_inherits_parent() -> None:
    fx = BlurSkia(id="fx")
    parent = _BusClip(id="el", bus_select="drums")
    assert resolve_effect_bus_select(fx, parent) == "drums"


def test_resolve_effect_bus_select_effect_override() -> None:
    fx = BlurSkia(id="fx", bus_select="vocals")
    parent = _BusClip(id="el", bus_select="drums")
    assert resolve_effect_bus_select(fx, parent) == "vocals"


def test_blur_smoothing_prepare_uses_parent_bus(tmp_path: Path) -> None:
    import asyncio

    fx = BlurSkia(id="fx", sensitivity=0.5, smoothing=0.0, bus_select=None)
    parent = _BusClip(id="bg", bus_select="main")
    frames = [
        AudioBusFrame(
            spectrum=[0.0] * 64,
            bass=0.01,
            mid=0.0,
            high=0.0,
            beat=False,
            amplitude=0.01,
        ),
        AudioBusFrame(
            spectrum=[0.0] * 64,
            bass=1.0,
            mid=0.0,
            high=0.0,
            beat=True,
            amplitude=1.0,
        ),
    ]
    ji = JobInfo(
        title="t",
        description="d",
        width=100,
        height=100,
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
    ctx = PrepareContext(
        job=ji, temp_dir=td, cache_dir=cd, audio={"main": frames}, parent_clip=parent
    )
    asyncio.run(fx.prepare(ctx))
    assert fx._smoothed_bass[1] == pytest.approx(1.0)  # noqa: SLF001


def test_blur_effective_radius_drops_to_zero_at_silence() -> None:
    fx = BlurSkia(id="fx", radius=10.0, sensitivity=1.0)
    fx._smoothed_bass = np.asarray([0.0], dtype=np.float32)  # noqa: SLF001
    assert fx._effective_radius(_blur_ctx()) == pytest.approx(0.0)  # noqa: SLF001


def test_blur_effective_radius_scales_up_at_full_bass() -> None:
    fx = BlurSkia(id="fx", radius=10.0, sensitivity=0.5)
    fx._smoothed_bass = np.asarray([1.0], dtype=np.float32)  # noqa: SLF001
    assert fx._effective_radius(_blur_ctx()) == pytest.approx(15.0)  # noqa: SLF001


def _blur_ctx(frame: int = 0) -> EffectContext:
    job = JobInfo(
        title="t",
        description="d",
        width=100,
        height=100,
        fps=30.0,
        duration=1.0,
        colors=ColorPalette(),
        typography=FontPalette(),
        locale="en",
    )
    return EffectContext(
        job=job,
        time=TimeState(frame=frame, t=frame / 30.0),
        bounds=Rect(0, 0, 100, 100),
        source=None,
        target=None,
    )


def test_blur_effective_radius_static_when_sensitivity_zero() -> None:
    fx = BlurSkia(id="fx", radius=4.0, sensitivity=0.0)
    assert fx._effective_radius(_blur_ctx()) == pytest.approx(4.0)  # noqa: SLF001
