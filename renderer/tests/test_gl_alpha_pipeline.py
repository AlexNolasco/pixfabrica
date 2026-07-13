"""GL FBO alpha contract — premultiplied pass through to Skia without double scaling."""

from __future__ import annotations

import asyncio

import numpy as np

from pixfabrica_core.audio.bus import N_SPECTRUM, AudioBusFrame
from pixfabrica_core.clips import JobInfo, PrepareContext, TimeState
from pixfabrica_core.composition.registry import register_clip_type
from pixfabrica_core.composition.track import FillLayout, GLTrack
from pixfabrica_core.fonts.skia_resolver import warmup_typography_palette
from pixfabrica_core.plugins.discovery import discover_plugins
from pixfabrica_core.theme.color import Color, ColorPalette
from pixfabrica_core.theme.typography import FontPalette
from pixfabrica_renderer.compositor import Compositor
from pixfabrica_std.audio.eq_led_gl import EqLedGL


def _register_plugins() -> None:
    for plugin in discover_plugins()[0]:
        for clip_cls in plugin.clip_types:
            register_clip_type(clip_cls)


async def _composite_eq_led(glow: float) -> np.ndarray:
    colors = ColorPalette(primary=Color("#00ccff"), background=Color("#101018"))
    ji = JobInfo(
        title="t",
        description="d",
        width=1920,
        height=1080,
        fps=30.0,
        duration=1.0,
        colors=colors,
        typography=FontPalette(),
        locale="en",
    )
    spec = np.linspace(0.2, 1.0, N_SPECTRUM, dtype=np.float32)
    frame = AudioBusFrame(
        amplitude=0.8,
        bass=0.8,
        mid=0.6,
        high=0.4,
        beat=False,
        spectrum=spec.tolist(),
    )
    audio = {"main": [frame] * 30}
    clip = EqLedGL(
        id="led",
        start=0.0,
        duration=1.0,
        bus_select="main",
        glow=glow,
        bar_count=32,
        max_bar_height=0.25,
    )
    track = GLTrack(id="t", start=0.0, duration=1.0, layout=FillLayout(), clips=[clip])
    ctx = PrepareContext.from_env(ji, audio=audio)
    warmup_typography_palette(ji.typography)
    await track.prepare(ctx)
    compositor = Compositor([track], ji, audio=audio)
    try:
        return np.array(compositor.composite(TimeState(frame=0, t=0.0)).toarray())
    finally:
        compositor.release_worker_resources()


def test_premul_pipeline_preserves_soft_glow_at_export() -> None:
    """Soft halos must survive GL blend + to_skia_bitmap (no alpha² crushing)."""
    _register_plugins()
    off = asyncio.run(_composite_eq_led(0.0))
    on = asyncio.run(_composite_eq_led(1.0))
    diff = np.abs(on.astype(np.int16) - off.astype(np.int16)).sum(axis=2)
    assert int((diff > 30).sum()) > 10_000
    assert float(diff.max()) > 100.0


def test_premul_pipeline_glow_below_baseline() -> None:
    _register_plugins()
    off = asyncio.run(_composite_eq_led(0.0))
    on = asyncio.run(_composite_eq_led(1.0))
    bright_on = on[:, :, :3].astype(np.int16).sum(axis=2) / 3
    bright_off = off[:, :, :3].astype(np.int16).sum(axis=2) / 3
    bg = float(np.percentile(bright_off, 10))
    y0 = int(1080 * 0.88)
    below = bright_on[y0:, :]
    below_off = bright_off[y0:, :]
    assert int((below > bg + 10).sum()) > 100
    assert float(below.mean()) > float(below_off.mean()) + 2.0
