"""Tests for std-mockup-eq key detection and layout helpers."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest
from PIL import Image as PILImage
from scipy import ndimage

from pixfabrica_core.audio.bus import N_SPECTRUM, AudioBusFrame
from pixfabrica_core.clips import JobInfo, PrepareContext, RenderContext, TimeState
from pixfabrica_core.graphics import Rect
from pixfabrica_core.prepare_diagnostics import PrepareDiagnostics
from pixfabrica_core.theme.color import Color, ColorPalette
from pixfabrica_core.theme.typography import FontPalette
from pixfabrica_std.image.mockup_eq import (
    MockupEq,
    SlotBackgroundMode,
    _apply_key_out,
    _bar_bin_slices,
    _bars_from_coarse_bands,
    _color_match_mask,
    _cover_fit,
    _find_blobs,
    _frame_to_bars,
    _freq_to_bars,
    _ImageBlob,
    _key_out_blob_rect,
    _map_blob_to_bounds,
    _normalize_bar_timeline,
    _resolve_slot_blobs,
    _segment_layout,
)


def _bounds() -> Rect:
    return Rect(0, 0, 1000, 500)


def _prepare_ctx(tmp_path: Path, *, audio: dict | None = None) -> PrepareContext:
    ji = JobInfo(
        title="t",
        description="d",
        width=1000,
        height=500,
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
    return PrepareContext(
        job=ji,
        temp_dir=td,
        cache_dir=cd,
        audio=audio or {},
        diagnostics=PrepareDiagnostics(),
    )


def _full_frame() -> AudioBusFrame:
    return AudioBusFrame(
        spectrum=[1.0] * N_SPECTRUM,
        bass=1.0,
        mid=1.0,
        high=1.0,
        beat=False,
        amplitude=1.0,
    )


def test_color_match_mask_respects_tolerance() -> None:
    rgba = np.zeros((4, 4, 4), dtype=np.uint8)
    rgba[..., :3] = (0, 255, 0)
    rgba[1, 1, :3] = (0, 245, 0)
    rgba[2, 2, :3] = (0, 200, 0)

    mask = _color_match_mask(rgba, Color("#00FF00"), tolerance=12)
    assert mask[0, 0]
    assert mask[1, 1]
    assert not mask[2, 2]


def test_find_blobs_picks_largest_first() -> None:
    mask = np.zeros((100, 200), dtype=bool)
    mask[10:20, 10:30] = True
    mask[40:90, 80:180] = True

    blobs = _find_blobs(mask, min_w=3, min_h=3)
    assert len(blobs) == 2
    assert blobs[0].area > blobs[1].area
    assert blobs[0].width == 100
    assert blobs[0].height == 50


def test_pad_slot_rect_expands_bounds() -> None:
    from pixfabrica_std.image.mockup_eq import _pad_slot_rect

    slot = Rect(10.0, 20.0, 100.0, 50.0)
    padded = _pad_slot_rect(slot, 2.0)
    assert padded.x == 8.0
    assert padded.y == 18.0
    assert padded.width == 104.0
    assert padded.height == 54.0


def test_cover_fit_maps_blob_into_bounds() -> None:
    cover = _cover_fit(2000.0, 1000.0, _bounds())
    blob = _find_blobs(np.ones((100, 100), dtype=bool), min_w=1, min_h=1)[0]
    mapped = _map_blob_to_bounds(blob, cover)
    assert mapped.width > 0.0
    assert mapped.height > 0.0
    assert _bounds().x <= mapped.x <= _bounds().x + _bounds().width


def test_key_out_blob_rect_clears_entire_box() -> None:
    rgba = np.full((20, 30, 4), 255, dtype=np.uint8)
    rgba[..., :3] = (0, 255, 0)
    blob = _ImageBlob(x=5, y=4, width=10, height=8, area=80)
    _key_out_blob_rect(rgba, blob)
    assert rgba[4:12, 5:15, 3].max() == 0
    assert rgba[4:12, 5:15, :3].max() == 0
    assert rgba[0, 0, 3] == 255


def test_normalize_bar_timeline_stretches_weak_analyzer_values() -> None:
    raw = np.array([[0.02, 0.01, 0.03], [0.08, 0.04, 0.06], [0.12, 0.05, 0.09]], dtype=np.float32)
    out = _normalize_bar_timeline(raw)
    assert out[-1, 0] == pytest.approx(1.0, abs=0.05)
    assert out[:, 1].max() > 0.5


def test_freq_to_bars_averages_log_slices() -> None:
    freq = np.linspace(0.0, 1.0, N_SPECTRUM, dtype=np.float32)
    slices = _bar_bin_slices(5)
    bars = _freq_to_bars(freq, slices)
    assert bars.shape == (5,)
    assert bars[0] < bars[-1]


def test_empty_spectrum_falls_back_to_band_interpolation() -> None:
    freq = np.zeros(N_SPECTRUM, dtype=np.float32)
    slices = _bar_bin_slices(24)
    spread = _frame_to_bars(freq, slices, bass=0.9, mid=0.5, high=0.2)
    assert spread.shape == (24,)
    assert spread[0] == pytest.approx(0.9, abs=0.01)
    assert spread[-1] == pytest.approx(0.2, abs=0.01)
    assert spread.std() > 0.05


def test_bars_from_coarse_bands_interpolates_three_anchors() -> None:
    bars = _bars_from_coarse_bands(1.0, 0.5, 0.0, 5)
    assert bars.tolist() == pytest.approx([1.0, 0.75, 0.5, 0.25, 0.0])


def test_resolve_slot_blobs_falls_back_to_soft_key_match() -> None:
    rgba = np.full((80, 80, 4), 255, dtype=np.uint8)
    rgba[..., :3] = (40, 40, 40)
    rgba[30:50, 30:50, :3] = (0, 250, 0)
    soft = _color_match_mask(rgba, Color("#00FF00"), tolerance=12)
    dilated = ndimage.binary_dilation(soft, iterations=2)
    blobs = _find_blobs(dilated, min_w=1, min_h=1)
    slot_blobs = _resolve_slot_blobs(rgba, Color("#00FF00"), min_w=1, min_h=1, dilated_blobs=blobs)
    assert slot_blobs
    assert slot_blobs[0].width == 20
    assert slot_blobs[0].height == 20


def test_prepare_finds_slot_when_key_is_near_green_not_exact(tmp_path: Path) -> None:
    img_path = tmp_path / "mockup.png"
    rgba = np.zeros((120, 200, 4), dtype=np.uint8)
    rgba[..., :3] = (30, 30, 30)
    rgba[..., 3] = 255
    rgba[20:40, 20:50, :3] = (0, 250, 0)
    PILImage.fromarray(rgba, mode="RGBA").save(img_path)

    clip = MockupEq(id="eq-soft", source=str(img_path))
    asyncio.run(clip.prepare(_prepare_ctx(tmp_path), _bounds()))

    assert clip._primary_slot is not None


def test_legacy_mockup_slot_mode_coerces_to_transparent() -> None:
    clip = MockupEq.model_validate(
        {"id": "eq-legacy-mockup", "slot_background_mode": "mockup"},
    )
    assert clip.slot_background_mode == SlotBackgroundMode.TRANSPARENT


def test_effective_slot_background_mode_legacy_custom() -> None:
    clip = MockupEq(id="eq-legacy", slot_background=Color("#112233"))
    assert clip._effective_slot_background_mode() == SlotBackgroundMode.CUSTOM

    transparent = MockupEq(id="eq-clear")
    assert transparent._effective_slot_background_mode() == SlotBackgroundMode.TRANSPARENT


def test_segment_layout_respects_minimum_segment_height() -> None:
    count, seg_h, gap_h = _segment_layout(100.0)
    assert count >= 1
    assert seg_h >= 3.5
    assert gap_h == pytest.approx(seg_h * 0.25)
    assert count * seg_h + (count - 1) * gap_h == pytest.approx(100.0, abs=0.01)


def test_apply_key_out_zeroes_alpha() -> None:
    rgba = np.zeros((2, 2, 4), dtype=np.uint8)
    rgba[..., :3] = (0, 255, 0)
    rgba[..., 3] = 255
    mask = np.ones((2, 2), dtype=bool)
    keyed = _apply_key_out(rgba, mask)
    assert keyed[..., 3].max() == 0


def test_prepare_records_diagnostic_when_no_key_region(tmp_path: Path) -> None:
    img_path = tmp_path / "mockup.png"
    PILImage.new("RGBA", (200, 100), (20, 20, 20, 255)).save(img_path)

    clip = MockupEq(id="eq-1", source=str(img_path), key_color=Color("#00FF00"))
    ctx = _prepare_ctx(tmp_path)
    asyncio.run(clip.prepare(ctx, _bounds()))

    assert clip._image is not None
    assert clip._primary_slot is None
    assert ctx.diagnostics is not None
    warnings = ctx.diagnostics.items()
    assert len(warnings) == 1
    assert warnings[0].code == "no_key_region"
    assert warnings[0].field == "key_color"


def test_prepare_detects_primary_and_extra_slots(tmp_path: Path) -> None:
    img_path = tmp_path / "mockup.png"
    rgba = np.zeros((120, 200, 4), dtype=np.uint8)
    rgba[..., :3] = (30, 30, 30)
    rgba[..., 3] = 255
    rgba[20:40, 20:50, :3] = (0, 255, 0)
    rgba[60:110, 120:190, :3] = (0, 255, 0)
    PILImage.fromarray(rgba, mode="RGBA").save(img_path)

    clip = MockupEq(id="eq-2", source=str(img_path))
    asyncio.run(clip.prepare(_prepare_ctx(tmp_path), _bounds()))

    assert clip._primary_slot is not None
    assert len(clip._extra_slots) == 1
    assert clip._primary_slot.width > clip._extra_slots[0].width


def test_draw_renders_bars_into_every_detected_slot(tmp_path: Path) -> None:
    img_path = tmp_path / "mockup.png"
    rgba = np.zeros((120, 200, 4), dtype=np.uint8)
    rgba[..., :3] = (30, 30, 30)
    rgba[..., 3] = 255
    rgba[20:40, 20:50, :3] = (0, 255, 0)  # primary — larger
    rgba[60:110, 120:190, :3] = (0, 255, 0)  # extra — different size
    PILImage.fromarray(rgba, mode="RGBA").save(img_path)

    ctx = _prepare_ctx(tmp_path, audio={"main": [_full_frame()] * 30})
    clip = MockupEq(id="eq-multi", source=str(img_path), bar_count=3)
    asyncio.run(clip.prepare(ctx, _bounds()))

    assert clip._primary_slot is not None
    assert len(clip._extra_slots) == 1
    assert clip._primary_slot.width != clip._extra_slots[0].width

    # bypass the percentile-normalized timeline (a constant-energy signal
    # normalizes to ~0) so every bar is fully lit and rendering is exercised.
    clip._bar_history = np.ones((30, clip.bar_count), dtype=np.float32)

    canvas = MagicMock()
    render = RenderContext(
        job=ctx.job,
        time=TimeState(frame=0, t=0.0),
        bounds=_bounds(),
        canvas=canvas,
    )
    clip.draw(render)

    # one outer clip from draw() plus one per rendered slot (primary + extras)
    assert canvas.clipRect.call_count == 2 + len(clip._extra_slots)
    assert canvas.drawRect.called


def test_prepare_slot_geometry_uses_exact_key_rect_not_dilated(tmp_path: Path) -> None:
    img_path = tmp_path / "mockup.png"
    rgba = np.zeros((60, 60, 4), dtype=np.uint8)
    rgba[..., :3] = (40, 40, 40)
    rgba[..., 3] = 255
    rgba[20:40, 20:40, :3] = (0, 255, 0)
    rgba[19, 20:40, :3] = (0, 250, 0)
    rgba[40, 20:40, :3] = (0, 250, 0)
    PILImage.fromarray(rgba, mode="RGBA").save(img_path)

    clip = MockupEq(id="eq-strict", source=str(img_path))
    asyncio.run(clip.prepare(_prepare_ctx(tmp_path), _bounds()))

    assert clip._primary_slot is not None
    cover = _cover_fit(60.0, 60.0, _bounds())
    slot_blob = _find_blobs(
        _color_match_mask(rgba, Color("#00FF00"), tolerance=0), min_w=1, min_h=1
    )[0]
    expected = _map_blob_to_bounds(slot_blob, cover)
    assert clip._primary_slot.x == pytest.approx(expected.x)
    assert clip._primary_slot.y == pytest.approx(expected.y)
    assert clip._primary_slot.width == pytest.approx(expected.width)
    assert clip._primary_slot.height == pytest.approx(expected.height)
