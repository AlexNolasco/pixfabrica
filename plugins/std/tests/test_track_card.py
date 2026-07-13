"""Tests for std-track-card layout helpers and upload policy wiring."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from pixfabrica_core.clips import JobInfo, RenderContext, TimeState
from pixfabrica_core.graphics import Rect
from pixfabrica_core.theme.color import ColorPalette
from pixfabrica_core.theme.typography import FontPalette
from pixfabrica_std.player._card_layout import (
    card_pivot,
    card_rect,
    ellipsize,
    is_vertical_sidebar_zone,
    normalized_perpendicular_angle,
    rotate_canvas_for_card,
    vertical_sidebar_rect,
)
from pixfabrica_std.player.track_card import TrackCard
from pixfabrica_std.text.skia_font import make_typography_font


def test_is_vertical_sidebar_zone() -> None:
    assert is_vertical_sidebar_zone(90.0)
    assert is_vertical_sidebar_zone(-90.0)
    assert is_vertical_sidebar_zone(75.0)
    assert is_vertical_sidebar_zone(105.0)
    assert not is_vertical_sidebar_zone(0.0)
    assert not is_vertical_sidebar_zone(45.0)
    assert not is_vertical_sidebar_zone(74.0)


def test_normalized_perpendicular_angle() -> None:
    assert normalized_perpendicular_angle(90.0) == pytest.approx(90.0)
    assert normalized_perpendicular_angle(-90.0) == pytest.approx(90.0)
    assert normalized_perpendicular_angle(0.0) == pytest.approx(0.0)


def test_vertical_sidebar_rect_swaps_width_and_height() -> None:
    bounds = Rect(0, 0, 1920, 1080)
    card = vertical_sidebar_rect(
        bounds,
        offset_x=0.5,
        offset_y=0.5,
        thickness_frac=0.12,
        span_frac=1.0,
    )
    assert card.width == pytest.approx(1080 * 0.12)
    assert card.height == pytest.approx(1080.0)


def test_track_card_vertical_sidebar_dimensions() -> None:
    bounds = Rect(0, 0, 1080, 1920)
    job = JobInfo(
        title="ACE-Step",
        description="d",
        width=int(bounds.width),
        height=int(bounds.height),
        fps=30.0,
        duration=10.0,
        colors=ColorPalette(),
        typography=FontPalette(),
        locale="en",
    )
    ctx = RenderContext(
        job=job,
        time=TimeState(frame=0, t=0.0),
        bounds=bounds,
        canvas=MagicMock(),
    )
    clip = TrackCard(id="tc", angle=90.0, width=1.0, band_height=0.12)
    card = clip._resolve_card_rect(ctx)
    assert card.width == pytest.approx(1920 * 0.12)
    assert card.height == pytest.approx(1920.0)


def test_ellipsize_truncates_long_text() -> None:
    font = make_typography_font(FontPalette().title_small)
    result = ellipsize("A Very Long Track Title That Should Not Fit", font, 120.0)
    assert result.endswith("...")
    assert font.measureText(result) <= 120.0 + 0.5


def test_ellipsize_keeps_short_text() -> None:
    font = make_typography_font(FontPalette().body_small)
    assert ellipsize("Short", font, 200.0) == "Short"


def test_card_rect_band_height_and_offsets() -> None:
    bounds = Rect(0, 0, 800, 400)
    card = card_rect(bounds, offset_x=0.5, offset_y=0.9, band_height=0.10)
    assert card.width == pytest.approx(800.0)
    assert card.height == pytest.approx(40.0)
    assert card.y == pytest.approx(360.0 - 20.0)


def test_card_rect_full_height_matches_bounds() -> None:
    bounds = Rect(10, 20, 300, 100)
    card = card_rect(bounds, offset_x=0.5, offset_y=0.5, band_height=1.0)
    assert card.x == pytest.approx(bounds.x)
    assert card.y == pytest.approx(bounds.y)
    assert card.width == pytest.approx(bounds.width)
    assert card.height == pytest.approx(bounds.height)


def test_card_pivot_matches_band_anchor() -> None:
    bounds = Rect(0, 0, 800, 400)
    assert card_pivot(bounds, offset_x=0.25, offset_y=0.9) == pytest.approx((200.0, 360.0))


def test_rotate_canvas_for_card_skips_zero_angle() -> None:
    canvas = MagicMock()
    bounds = Rect(0, 0, 100, 50)
    rotate_canvas_for_card(canvas, bounds, angle=0.0, offset_x=0.5, offset_y=0.5)
    canvas.rotate.assert_not_called()


def test_rotate_canvas_for_card_uses_band_pivot() -> None:
    canvas = MagicMock()
    bounds = Rect(10, 20, 200, 100)
    rotate_canvas_for_card(canvas, bounds, angle=15.0, offset_x=0.5, offset_y=0.75)
    canvas.rotate.assert_called_once_with(15.0, 110.0, 95.0)


def test_track_card_draws_progress_and_transport() -> None:
    bounds = Rect(0, 0, 800, 200)
    canvas = MagicMock()
    job = JobInfo(
        title="t",
        description="d",
        width=int(bounds.width),
        height=int(bounds.height),
        fps=30.0,
        duration=10.0,
        colors=ColorPalette(),
        typography=FontPalette(),
        locale="en",
    )
    ctx = RenderContext(
        job=job,
        time=TimeState(frame=15, t=0.5),
        bounds=bounds,
        canvas=canvas,
    )
    clip = TrackCard(
        id="tc",
        start=0.0,
        duration=2.0,
        title="Track",
        author="Artist",
        transport_state="pause",
    )
    with patch("pixfabrica_std.player.track_card.draw_transport_icon"):
        clip.draw(ctx)

    assert canvas.drawRect.called
    assert canvas.drawRRect.called
    assert canvas.drawString.call_count >= 2


def test_track_card_panel_full_bleed_when_untilted() -> None:
    bounds = Rect(0, 0, 800, 200)
    canvas = MagicMock()
    job = JobInfo(
        title="t",
        description="d",
        width=int(bounds.width),
        height=int(bounds.height),
        fps=30.0,
        duration=10.0,
        colors=ColorPalette(),
        typography=FontPalette(),
        locale="en",
    )
    ctx = RenderContext(
        job=job,
        time=TimeState(frame=0, t=0.0),
        bounds=bounds,
        canvas=canvas,
    )
    clip = TrackCard(id="tc", angle=0.0)
    card = clip._resolve_card_rect(ctx)
    assert card.width == pytest.approx(800.0)
    with patch("pixfabrica_std.player.track_card.draw_transport_icon"):
        clip.draw(ctx)


def test_track_card_tilted_band_expands_for_geometry() -> None:
    bounds = Rect(0, 0, 1920, 1080)
    canvas = MagicMock()
    job = JobInfo(
        title="Summer Nights",
        description="d",
        width=int(bounds.width),
        height=int(bounds.height),
        fps=30.0,
        duration=10.0,
        colors=ColorPalette(),
        typography=FontPalette(),
        locale="en",
    )
    ctx = RenderContext(
        job=job,
        time=TimeState(frame=0, t=0.0),
        bounds=bounds,
        canvas=canvas,
    )
    clip = TrackCard(
        id="tc",
        angle=45.0,
        width=0.6,
        offset_x=0.5,
        offset_y=0.5,
        title="Summer Nights",
        author="Artist",
    )
    card = clip._resolve_card_rect(ctx)
    assert card.width >= 0.6 * bounds.width
    assert card.width > bounds.height * 0.12 * 1.5
    with patch("pixfabrica_std.player.track_card.draw_transport_icon"):
        clip.draw(ctx)
    panel = canvas.drawRRect.call_args[0][0]
    assert panel.rect().width() == pytest.approx(card.width)


def test_track_card_skips_panel_when_background_null() -> None:
    bounds = Rect(0, 0, 800, 200)
    canvas = MagicMock()
    job = JobInfo(
        title="t",
        description="d",
        width=int(bounds.width),
        height=int(bounds.height),
        fps=30.0,
        duration=10.0,
        colors=ColorPalette(),
        typography=FontPalette(),
        locale="en",
    )
    ctx = RenderContext(
        job=job,
        time=TimeState(frame=0, t=0.0),
        bounds=bounds,
        canvas=canvas,
    )
    clip = TrackCard(id="tc", background=None)
    with (
        patch("pixfabrica_std.player.track_card.draw_panel_background") as mock_panel,
        patch("pixfabrica_std.player.track_card.draw_transport_icon"),
    ):
        clip.draw(ctx)
    mock_panel.assert_not_called()


def test_track_card_skips_progress_when_height_zero() -> None:
    bounds = Rect(0, 0, 800, 200)
    canvas = MagicMock()
    job = JobInfo(
        title="t",
        description="d",
        width=int(bounds.width),
        height=int(bounds.height),
        fps=30.0,
        duration=10.0,
        colors=ColorPalette(),
        typography=FontPalette(),
        locale="en",
    )
    ctx = RenderContext(
        job=job,
        time=TimeState(frame=15, t=0.5),
        bounds=bounds,
        canvas=canvas,
    )
    clip = TrackCard(id="tc", progress_height=0.0, background=None)
    with patch("pixfabrica_std.player.track_card.draw_transport_icon"):
        clip.draw(ctx)
    canvas.drawRect.assert_not_called()


def test_track_card_source_max_px_respects_cover_scale() -> None:
    bounds = Rect(0, 0, 1000, 500)
    small = TrackCard.source_max_px(
        bounds,
        cover_scale=0.5,
        progress_height=0.0,
        band_height=1.0,
    )
    large = TrackCard.source_max_px(
        bounds,
        cover_scale=1.0,
        progress_height=0.0,
        band_height=1.0,
    )
    assert small < large


def test_track_card_width_scales_band() -> None:
    bounds = Rect(0, 0, 800, 400)
    job = JobInfo(
        title="t",
        description="d",
        width=int(bounds.width),
        height=int(bounds.height),
        fps=30.0,
        duration=10.0,
        colors=ColorPalette(),
        typography=FontPalette(),
        locale="en",
    )
    ctx = RenderContext(
        job=job,
        time=TimeState(frame=0, t=0.0),
        bounds=bounds,
        canvas=MagicMock(),
    )
    full = TrackCard(id="tc", width=1.0, angle=0.0)
    half = TrackCard(id="tc2", width=0.5, angle=0.0)
    assert full._resolve_card_rect(ctx).width == pytest.approx(800.0)
    assert half._resolve_card_rect(ctx).width == pytest.approx(400.0)
