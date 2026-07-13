"""One-off GL preview profiling — per-track composite timings at preview resolution."""

from __future__ import annotations

import asyncio
import statistics
import time
from collections import defaultdict
from typing import Any, cast

from pixfabrica_core.clips.base import Clip, JobInfo, PrepareContext, TimeState
from pixfabrica_core.composition.registry import register_clip_type, register_setting_type
from pixfabrica_core.composition.track import GLEffectTrack, GLTrack, SkiaTrack
from pixfabrica_core.fonts.skia_resolver import warmup_typography_palette
from pixfabrica_core.plugins.discovery import discover_plugins
from pixfabrica_core.preview_dims import preview_dimensions
from pixfabrica_core.theme.color import Color, ColorPalette, ColorToken
from pixfabrica_core.theme.typography import FontPalette
from pixfabrica_renderer.compositor import Compositor


def _register_plugins() -> None:
    for plugin in discover_plugins()[0]:
        for clip_cls in plugin.clip_types:
            register_clip_type(clip_cls)
        for cfg_cls in plugin.project_settings:
            register_setting_type(cfg_cls)


def _colors() -> ColorPalette:
    return ColorPalette(
        primary=Color("#FA0202"),
        secondary=Color("#00D423"),
        tertiary=Color("#4488ff"),
        accent=Color("#ffcc00"),
        background=Color("#0a0a12"),
        neutral=Color("#888888"),
        neutral_variant=Color("#444444"),
    )


def _job_info(w: int, h: int) -> JobInfo:
    return JobInfo(
        title="profile",
        description="",
        width=w,
        height=h,
        fps=30.0,
        duration=10.0,
        locale="en",
        colors=_colors(),
        typography=FontPalette(),
    )


def _dying_universe_track(star_count: int = 80) -> GLTrack:
    from pixfabrica_std.particles.dying_universe_gl import DyingUniverseGL

    return GLTrack(
        id="gl-dying",
        start=0.0,
        duration=10.0,
        clips=[
            DyingUniverseGL(
                id="dying",
                start=0.0,
                duration=10.0,
                star_count=star_count,
            )
        ],
    )


def _hex_track() -> GLTrack:
    from pixfabrica_std.background.hex_background_gl import HexBackgroundGL

    return GLTrack(
        id="gl-hex",
        start=0.0,
        duration=10.0,
        clips=[
            HexBackgroundGL(
                id="hex",
                start=0.0,
                duration=10.0,
            )
        ],
    )


def _solid_skia_track() -> SkiaTrack:
    from pixfabrica_std.background.solid_background import SolidBackground

    return SkiaTrack(
        id="skia-solid",
        start=0.0,
        duration=10.0,
        clips=cast(
            list[Clip],
            [
                SolidBackground(
                    id="solid",
                    start=0.0,
                    duration=10.0,
                    color=ColorToken.BACKGROUND,
                )
            ],
        ),
    )


def _water_drops_track() -> GLEffectTrack:
    from pixfabrica_std.effects.water_drops_gl import WaterDropsGL

    return GLEffectTrack(
        id="post-rain",
        start=0.0,
        duration=10.0,
        clips=[
            WaterDropsGL(
                id="rain",
                start=0.0,
                duration=10.0,
            )
        ],
    )


async def _prepare_compositor(tracks: list[Any], w: int, h: int) -> Compositor:
    ji = _job_info(w, h)
    ctx = PrepareContext.from_env(ji)
    warmup_typography_palette(ji.typography)
    for track in tracks:
        await track.prepare(ctx)
    return Compositor(tracks, ji)


def _profile(
    compositor: Compositor,
    *,
    label: str,
    t: float = 2.5,
    warmup: int = 3,
    frames: int = 20,
) -> dict[str, float | str]:
    track_ms: dict[str, list[float]] = defaultdict(list)
    total_ms: list[float] = []

    original = compositor._render_track

    def timed_render(self: Compositor, track: Any, ts: TimeState, canvas: Any) -> None:
        t0 = time.perf_counter()
        original(track, ts, canvas)
        track_ms[track.id].append((time.perf_counter() - t0) * 1000)

    compositor._render_track = timed_render.__get__(compositor, Compositor)  # type: ignore[method-assign]

    ts = TimeState(frame=int(t * compositor._job_info.fps), t=t)
    for _ in range(warmup):
        compositor.composite(ts)

    for _ in range(frames):
        t0 = time.perf_counter()
        compositor.composite(ts)
        total_ms.append((time.perf_counter() - t0) * 1000)

    compositor._render_track = original  # type: ignore[method-assign]

    per_track = {tid: statistics.mean(samples) for tid, samples in track_ms.items()}
    return {
        "label": label,
        "pixels": compositor._job_info.width * compositor._job_info.height,
        "total_ms": statistics.mean(total_ms),
        "total_fps": 1000.0 / statistics.mean(total_ms),
        **{f"track_{tid}_ms": ms for tid, ms in sorted(per_track.items())},
    }


async def main() -> None:
    _register_plugins()

    job_w, job_h = 1080, 1920
    preview_w, preview_h = preview_dimensions(job_w, job_h)
    print(
        f"Project {job_w}x{job_h} -> preview {preview_w}x{preview_h} ({preview_w * preview_h:,} px)"
    )
    print()

    scenarios: list[tuple[str, list[Any]]] = [
        ("hex only", [_hex_track()]),
        ("dying universe star_count=80", [_dying_universe_track(80)]),
        ("dying universe star_count=40", [_dying_universe_track(40)]),
        ("dying universe star_count=25", [_dying_universe_track(25)]),
        ("solid + water drops", [_solid_skia_track(), _water_drops_track()]),
        ("hex + water drops", [_hex_track(), _water_drops_track()]),
        ("dying + water drops", [_dying_universe_track(80), _water_drops_track()]),
        ("dying(40) + water drops", [_dying_universe_track(40), _water_drops_track()]),
    ]

    rows: list[dict[str, float | str]] = []
    for label, tracks in scenarios:
        comp = await _prepare_compositor(tracks, preview_w, preview_h)
        try:
            rows.append(_profile(comp, label=label))
        finally:
            comp.release_worker_resources()

    print(f"{'Scenario':<28} {'total':>8} {'fps':>6}  per-track breakdown")
    print("-" * 72)
    for row in rows:
        tracks = [
            f"{k.removeprefix('track_').removesuffix('_ms')}={v:.1f}ms"
            for k, v in row.items()
            if k.startswith("track_")
        ]
        track_str = ", ".join(tracks) if tracks else "(none)"
        print(f"{row['label']:<28} {row['total_ms']:>7.1f}ms {row['total_fps']:>5.1f}  {track_str}")


if __name__ == "__main__":
    asyncio.run(main())
