"""Tests for std-music-room-gl."""

from __future__ import annotations

from pathlib import Path

import moderngl
import numpy as np
import pytest

from pixfabrica_core.audio.bus import N_SPECTRUM, AudioBusFrame
from pixfabrica_core.clips import JobInfo, PrepareContext
from pixfabrica_core.graphics import Rect
from pixfabrica_core.theme.color import ColorPalette
from pixfabrica_core.theme.typography import FontPalette
from pixfabrica_std.background.music_room_gl import (
    _FRAG,
    _MAX_BARS,
    _NUM_WALLS,
    _PEAK_FALL,
    _PEAK_HOLD,
    _VERT,
    MusicRoomGL,
    _bars_from_spectrum,
    _bars_texture_bytes,
    _fit_uv_transform,
    _pad_bars_texture,
    _precompute_bars_and_peaks,
)
from pixfabrica_std.common import FitMode


def _prepare_ctx(tmp_path: Path, *, duration_sec: float = 1.0) -> PrepareContext:
    ji = JobInfo(
        title="t",
        description="d",
        width=640,
        height=480,
        fps=30.0,
        duration=duration_sec,
        colors=ColorPalette(),
        typography=FontPalette(),
        locale="en",
    )
    td = tmp_path / "temp"
    cd = tmp_path / "cache"
    td.mkdir(exist_ok=True)
    cd.mkdir(exist_ok=True)
    return PrepareContext(job=ji, temp_dir=td, cache_dir=cd, audio={})


def test_declares_texture_upload_policies() -> None:
    from pixfabrica_core.file_upload_policy import JobBoundsFactorPolicy

    policies = MusicRoomGL.file_upload_policies()
    assert set(policies) == {"wall_source", "floor_source"}
    assert isinstance(policies["wall_source"], JobBoundsFactorPolicy)
    assert MusicRoomGL.texture_source_max_px(Rect(0, 0, 1920, 1080)) == 2880


def test_music_room_wall_and_floor_sources_are_file_controls() -> None:
    from pixfabrica_cli.commands.gen_ui import _build_controls_for_class

    controls, unknowns, _ = _build_controls_for_class(MusicRoomGL)
    assert not unknowns
    for field in ("wall_source", "floor_source"):
        ctrl = controls[field]
        assert ctrl["kind"] == "file"
        assert ctrl["upload_kind"] == "image"
        assert ctrl.get("nullable") is True
        assert ctrl.get("stock_browse") is True
        assert ".png" in ctrl["accept"]
    assert controls["wall_source_attribution"]["kind"] == "textarea"
    assert controls["wall_source_provider"]["kind"] == "hidden"


def test_file_upload_policy_index_includes_music_room() -> None:
    from pixfabrica_core.file_upload_policy import build_file_upload_policy_index
    from pixfabrica_std import Plugin

    index = build_file_upload_policy_index([Plugin])
    assert ("std-music-room-gl", "wall_source") in index
    assert ("std-music-room-gl", "floor_source") in index


def test_clip_type_registered() -> None:
    assert MusicRoomGL.clip_type == "std-music-room-gl"


def test_float_textures_accept_bar_and_peak_bytes() -> None:
    gl = moderngl.create_standalone_context()
    bars = np.ones((_MAX_BARS, _NUM_WALLS), dtype=np.float32) * 0.5
    peaks = np.ones((_MAX_BARS, _NUM_WALLS), dtype=np.float32) * 0.5
    bars_tex = gl.texture((_MAX_BARS, _NUM_WALLS), 1, dtype="f4")
    bars_tex.write(bars.tobytes())
    peak_tex = gl.texture((_MAX_BARS, _NUM_WALLS), 1, dtype="f4")
    peak_tex.write(peaks.tobytes())


def test_bars_texture_bytes_layout_matches_texel_fetch() -> None:
    gl = moderngl.create_standalone_context()
    bars = np.zeros((_MAX_BARS, _NUM_WALLS), dtype=np.float32)
    bars[5, 2] = 0.75
    bars[17, 3] = 0.42
    tex = gl.texture((_MAX_BARS, _NUM_WALLS), 1, dtype="f4")
    tex.write(_bars_texture_bytes(bars))
    raw = np.frombuffer(tex.read(), dtype=np.float32).reshape(_NUM_WALLS, _MAX_BARS)
    assert raw[2, 5] == pytest.approx(0.75)
    assert raw[3, 17] == pytest.approx(0.42)


def test_eq_color_fields_default_to_theme_tokens() -> None:
    clip = MusicRoomGL(id="mr")
    from pixfabrica_core.theme.color import ColorToken

    assert clip.eq_color_low == ColorToken.PRIMARY
    assert clip.eq_color_high == ColorToken.SECONDARY


def test_has_user_image_detects_placeholder() -> None:
    from pixfabrica_std.background.music_room_gl import _BLACK_RGB, _has_user_image

    assert not _has_user_image(_BLACK_RGB)
    assert _has_user_image(np.zeros((64, 64, 3), dtype=np.uint8))


def test_shader_compiles() -> None:
    ctx = moderngl.create_standalone_context()
    ctx.program(vertex_shader=_VERT, fragment_shader=_FRAG)


def test_presets_include_variants() -> None:
    presets = {p["id"]: p for p in MusicRoomGL.clip_presets}
    assert "default" in presets
    assert presets["default"]["label"] == "Neon Room"
    assert "slow_lounge" in presets
    assert "club" in presets


def test_light_intensity_default() -> None:
    clip = MusicRoomGL(id="mr")
    assert clip.light_intensity == 1.0


def test_wall_vividness_default() -> None:
    clip = MusicRoomGL(id="mr")
    assert clip.wall_vividness == 1.5


def test_bar_count_default_is_max() -> None:
    clip = MusicRoomGL(id="mr")
    assert clip.bar_count == _MAX_BARS


def test_max_bars_constant_is_32() -> None:
    assert _MAX_BARS == 32


def test_peak_hold_snaps_up_then_decays() -> None:
    fps = 30.0
    hold_frames = int(_PEAK_HOLD * fps)
    fall_frames = int(_PEAK_FALL * fps) + 5
    total = 1 + hold_frames + fall_frames
    loud = AudioBusFrame(
        spectrum=[1.0 if i < 8 else 0.0 for i in range(N_SPECTRUM)],
        bass=1.0,
        mid=0.5,
        high=0.2,
        amplitude=1.0,
        beat=False,
    )
    quiet = AudioBusFrame(
        spectrum=[0.0] * N_SPECTRUM,
        bass=0.0,
        mid=0.0,
        high=0.0,
        amplitude=0.0,
        beat=False,
    )
    frames = [loud] + [quiet] * (total - 1)
    _, peaks = _precompute_bars_and_peaks(
        total_frames=total,
        fps=fps,
        sensitivity=1.0,
        bus_frames=frames,
    )
    assert peaks.shape == (total, _MAX_BARS, 4)
    assert peaks[0, 0, 0] >= 0.5
    assert peaks[hold_frames + 1, 0, 0] >= peaks[0, 0, 0] * 0.5
    assert peaks[-1, 0, 0] < peaks[hold_frames + 1, 0, 0]


def test_demo_precompute_without_bus() -> None:
    bars, peaks = _precompute_bars_and_peaks(
        total_frames=60,
        fps=30.0,
        sensitivity=1.0,
        bus_frames=None,
    )
    assert bars.shape == (60, _MAX_BARS, _NUM_WALLS)
    assert peaks.shape == (60, _MAX_BARS, _NUM_WALLS)
    assert float(bars.max()) > 0.01
    assert float(peaks.max()) > 0.01


def test_bar_levels_wall_offset_differs() -> None:
    spec = np.linspace(0.0, 1.0, N_SPECTRUM, dtype=np.float32)
    levels = _bars_from_spectrum(spec, _MAX_BARS)
    assert levels[4, 0] != pytest.approx(levels[4, 1])


def test_bars_from_spectrum_respects_bar_count() -> None:
    spec = np.linspace(0.0, 1.0, N_SPECTRUM, dtype=np.float32)
    levels = _bars_from_spectrum(spec, 8)
    assert levels.shape == (8, _NUM_WALLS)
    padded = _pad_bars_texture(levels)
    assert padded.shape == (_MAX_BARS, _NUM_WALLS)
    assert float(padded[8:].sum()) == 0.0


def test_precompute_with_zero_bars_is_silent() -> None:
    bars, peaks = _precompute_bars_and_peaks(
        total_frames=30,
        fps=30.0,
        sensitivity=1.0,
        bus_frames=None,
        bar_count=0,
    )
    assert bars.shape == (30, _MAX_BARS, _NUM_WALLS)
    assert float(bars.max()) == 0.0
    assert float(peaks.max()) == 0.0


def test_fit_uv_stretch_fills_destination() -> None:
    fit, contain = _fit_uv_transform(FitMode.STRETCH, 800.0, 600.0, 16.0, 5.0)
    assert fit == pytest.approx((1.0, 1.0, 0.0, 0.0))
    assert contain == 0.0


def test_fit_uv_cover_crops_wide_source() -> None:
    # 2:1 image on 2:1 wall face → full cover, no offset
    fit, contain = _fit_uv_transform(FitMode.COVER, 1600.0, 800.0, 16.0, 8.0)
    assert fit == pytest.approx((1.0, 1.0, 0.0, 0.0))
    assert contain == 0.0

    # Wide image on slightly narrower wall → vertical fill, horizontal crop
    fit, contain = _fit_uv_transform(FitMode.COVER, 1600.0, 900.0, 16.0, 10.0)
    assert fit[0] > 1.0
    assert fit[1] == pytest.approx(1.0)
    assert contain == 0.0


def test_fit_uv_contain_letterboxes() -> None:
    fit, contain = _fit_uv_transform(FitMode.CONTAIN, 900.0, 1600.0, 16.0, 10.0)
    assert fit[0] < 1.0
    assert fit[1] == pytest.approx(1.0)
    assert contain == 1.0


@pytest.mark.asyncio
async def test_prepare_builds_histories(tmp_path: Path) -> None:
    bus = [
        AudioBusFrame(
            spectrum=[0.5] * N_SPECTRUM,
            bass=0.5,
            mid=0.3,
            high=0.2,
            amplitude=0.5,
            beat=False,
        )
        for _ in range(30)
    ]
    ji = JobInfo(
        title="t",
        description="d",
        width=640,
        height=480,
        fps=30.0,
        duration=1.0,
        colors=ColorPalette(),
        typography=FontPalette(),
        locale="en",
    )
    td = tmp_path / "temp"
    cd = tmp_path / "cache"
    td.mkdir(exist_ok=True)
    cd.mkdir(exist_ok=True)
    ctx = PrepareContext(job=ji, temp_dir=td, cache_dir=cd, audio={"main": bus})
    clip = MusicRoomGL(id="mr", bus_select="main")
    await clip.prepare(ctx)
    assert clip._bar_history.shape[0] == 30
    assert clip._peak_history.shape == (30, _MAX_BARS, _NUM_WALLS)
