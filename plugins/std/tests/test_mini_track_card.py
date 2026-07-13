"""Tests for std-mini-track-card."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from pixfabrica_core.clips import JobInfo, RenderContext, TimeState
from pixfabrica_core.graphics import Rect
from pixfabrica_core.theme.color import ColorPalette
from pixfabrica_core.theme.typography import FontPalette
from pixfabrica_std.player._card_layout import (
    MINI_PADDING_Y,
    MINI_TEXT_GAP,
    card_rect,
    content_rect,
    ellipsize,
    is_vertical_sidebar_zone,
)
from pixfabrica_std.player.mini_track_card import MiniTrackCard
from pixfabrica_std.text.skia_font import make_typography_font


def test_mini_card_rect_default_bottom_band() -> None:
    bounds = Rect(0, 0, 800, 400)
    card = card_rect(bounds, offset_x=0.5, offset_y=0.9, band_height=0.10)
    assert card.width == pytest.approx(800.0)
    assert card.x == pytest.approx(0.0)
    assert card.height == pytest.approx(40.0)
    assert card.y == pytest.approx(360.0 - 20.0)


def test_mini_track_card_panel_spans_full_band_width() -> None:
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
    clip = MiniTrackCard(id="mini", title="Track", author="Artist")
    card = clip._resolve_card_rect(ctx)
    assert card.width == pytest.approx(800.0)
    clip.draw(ctx)

    panel_call = canvas.drawRRect.call_args[0][0]
    assert panel_call.rect().width() == pytest.approx(800.0)
    assert panel_call.rect().x() == pytest.approx(-400.0)


def test_mini_track_card_draws_panel_and_text() -> None:
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
    clip = MiniTrackCard(id="mini", title="Track", author="Artist")
    clip.draw(ctx)

    assert canvas.drawRRect.called
    assert canvas.drawString.call_count >= 2


def test_mini_track_card_tilted_panel_narrower_than_bounds() -> None:
    bounds = Rect(0, 0, 1920, 1080)
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
    clip = MiniTrackCard(
        id="mini",
        angle=45.0,
        offset_x=0.5,
        offset_y=0.5,
        title="Summer Nights",
        author="Artist",
    )
    clip.draw(ctx)
    panel = canvas.drawRRect.call_args[0][0]
    assert panel.rect().width() == pytest.approx(bounds.width)
    assert panel.rect().height() == pytest.approx(bounds.height * 0.12)


def test_mini_track_card_cover_has_matching_side_gaps() -> None:
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
    clip = MiniTrackCard(id="mini", title="Track", author="Artist")
    clip._cover_image = MagicMock()
    clip.draw(ctx)

    card = clip._resolve_card_rect(ctx)
    local_card = Rect(-card.width / 2.0, -card.height / 2.0, card.width, card.height)
    content = content_rect(local_card, 0.0, MINI_PADDING_Y)
    gap_px = MINI_TEXT_GAP * content.width

    cover_clip = canvas.clipRRect.call_args[0][0]
    assert cover_clip.rect().x() == pytest.approx(content.x + gap_px)


def test_mini_track_card_upload_policy() -> None:
    from pixfabrica_core.file_upload_policy import ContentThumbFactorPolicy

    policy = MiniTrackCard.source_upload_policy()
    assert isinstance(policy, ContentThumbFactorPolicy)


def test_mini_track_card_vertical_sidebar_dimensions() -> None:
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
    clip = MiniTrackCard(id="mini", angle=90.0, band_height=0.12)
    card = clip._resolve_card_rect(ctx)
    assert card.width == pytest.approx(1920 * 0.12)
    assert card.height == pytest.approx(1920.0)


def test_is_vertical_sidebar_zone_mini() -> None:
    assert is_vertical_sidebar_zone(90.0)
    assert not is_vertical_sidebar_zone(45.0)


def test_ellipsize_reexport() -> None:
    font = make_typography_font(FontPalette().title_small)
    assert ellipsize("Hello", font, 200.0) == "Hello"
