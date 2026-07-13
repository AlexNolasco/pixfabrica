"""Tests for std-info-track-card."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from pixfabrica_core.clips import JobInfo, RenderContext, TimeState
from pixfabrica_core.graphics import Rect
from pixfabrica_core.theme.color import ColorPalette
from pixfabrica_core.theme.typography import FontPalette
from pixfabrica_std.player._card_layout import card_rect, wrap_text_lines
from pixfabrica_std.player.info_track_card import InfoTrackCard
from pixfabrica_std.text.skia_font import make_typography_font


def test_info_card_default_band_geometry() -> None:
    bounds = Rect(0, 0, 800, 400)
    card = card_rect(bounds, offset_x=0.5, offset_y=0.88, band_height=0.26)
    assert card.width == pytest.approx(800.0)
    assert card.height == pytest.approx(104.0)


def test_wrap_text_lines_two_line_cap() -> None:
    font = make_typography_font(FontPalette().title_medium)
    lines = wrap_text_lines(
        "A Very Long Track Title That Should Wrap To Two Lines Maximum",
        font,
        220.0,
        max_lines=2,
    )
    assert 1 <= len(lines) <= 2


def test_info_track_card_draws_panel_transport_and_rows() -> None:
    bounds = Rect(0, 0, 800, 400)
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
    clip = InfoTrackCard(id="info")
    with (
        patch(
            "pixfabrica_std.player.info_track_card.resolve_info_date",
            return_value=date(2026, 6, 13),
        ),
        patch("pixfabrica_std.player.info_track_card.draw_transport_icon"),
        patch("pixfabrica_std.player.info_track_card.draw_row_icon"),
    ):
        clip.draw(ctx)

    assert canvas.drawRRect.called
    assert canvas.drawString.call_count >= 4


def test_info_track_card_hides_zero_stats() -> None:
    clip = InfoTrackCard(id="info", likes=0, comments=0, replays=0, play_count=0, duration=0.0)
    assert clip._stat_segments("en") == []
    with patch(
        "pixfabrica_std.player.info_track_card.resolve_info_date",
        return_value=date(2026, 6, 13),
    ):
        meta = clip._meta_segments("en", span_sec=0.0)
    assert len(meta) == 1
    assert meta[0].text == "Jun 13, 2026"


def test_info_track_card_duration_from_clip_span() -> None:
    clip = InfoTrackCard(id="info", duration=222.0)
    meta = clip._meta_segments("en", span_sec=222.0)
    assert any(segment.text == "3:42" for segment in meta)

    clip_no_duration = InfoTrackCard(id="info")
    meta_job = clip_no_duration._meta_segments("en", span_sec=10.0)
    assert any(segment.text == "0:10" for segment in meta_job)


def test_info_track_card_panel_full_bleed_width_when_untilted() -> None:
    bounds = Rect(0, 0, 800, 400)
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
    clip = InfoTrackCard(id="info", angle=0.0)
    with (
        patch("pixfabrica_std.player.info_track_card.draw_transport_icon"),
        patch("pixfabrica_std.player.info_track_card.draw_row_icon"),
    ):
        clip.draw(ctx)
    panel = canvas.drawRRect.call_args[0][0]
    assert panel.rect().width() == pytest.approx(800.0)


def test_info_track_card_tilted_panel_narrower_than_bounds() -> None:
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
    clip = InfoTrackCard(
        id="info",
        angle=45.0,
        offset_x=0.5,
        offset_y=0.5,
    )
    with (
        patch("pixfabrica_std.player.info_track_card.draw_transport_icon"),
        patch("pixfabrica_std.player.info_track_card.draw_row_icon"),
    ):
        clip.draw(ctx)
    panel = canvas.drawRRect.call_args[0][0]
    assert panel.rect().width() == pytest.approx(bounds.width)
    assert panel.rect().height() == pytest.approx(bounds.height * 0.26)


def test_info_track_card_skips_panel_when_background_null() -> None:
    bounds = Rect(0, 0, 800, 400)
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
    clip = InfoTrackCard(id="info", background=None)
    with (
        patch("pixfabrica_std.player.info_track_card.draw_transport_icon"),
        patch("pixfabrica_std.player.info_track_card.draw_row_icon"),
    ):
        clip.draw(ctx)

    assert not canvas.drawRRect.called


def test_info_track_card_demo_defaults() -> None:
    clip = InfoTrackCard(id="info")
    assert clip.title == "{TITLE}"
    assert clip.play_count == 199_000
    assert clip.duration is None
    assert clip.band_height == pytest.approx(0.26)


def test_info_track_card_vertical_sidebar_dimensions() -> None:
    bounds = Rect(0, 0, 1080, 1920)
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
    clip = InfoTrackCard(id="info", angle=90.0, band_height=0.26)
    card = clip._resolve_card_rect(ctx)
    assert card.width == pytest.approx(1920 * 0.26)
    assert card.height == pytest.approx(1920.0)


def test_info_track_card_vertical_sidebar_draws_transport() -> None:
    bounds = Rect(0, 0, 1080, 1920)
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
    clip = InfoTrackCard(id="info", angle=90.0, transport_state="play")
    with (
        patch(
            "pixfabrica_std.player.info_track_card.resolve_info_date",
            return_value=date(2026, 6, 13),
        ),
        patch("pixfabrica_std.player.info_track_card.draw_transport_icon") as draw_transport,
        patch("pixfabrica_std.player.info_track_card.draw_row_icon"),
    ):
        clip.draw(ctx)

    draw_transport.assert_called_once()
