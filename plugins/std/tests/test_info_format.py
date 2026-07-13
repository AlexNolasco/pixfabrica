"""Tests for std-info-track-card formatting helpers."""

from __future__ import annotations

from datetime import UTC, date

from pixfabrica_std.player._info_format import (
    format_duration,
    format_grouped_count,
    format_medium_date,
    format_play_count,
    resolve_info_date,
)


def test_format_play_count_abbreviates_at_ten_thousand() -> None:
    assert format_play_count(199_000, "en") == "199K"
    assert format_play_count(9999, "en") == "9,999"


def test_format_grouped_count_locale() -> None:
    assert format_grouped_count(1245, "en") == "1,245"
    assert format_grouped_count(1245, "es") == "1.245"


def test_format_duration_short_and_long() -> None:
    assert format_duration(222) == "3:42"
    assert format_duration(3930) == "1:05:30"


def test_format_medium_date_localized() -> None:
    value = date(2026, 6, 13)
    assert format_medium_date(value, "en") == "Jun 13, 2026"
    assert format_medium_date(value, "es") == "13 jun 2026"
    assert format_medium_date(value, "zh-CN") == "2026年6月13日"


def test_resolve_info_date_defaults_to_now() -> None:
    from datetime import datetime

    now = datetime(2026, 6, 13, 12, 0, tzinfo=UTC)
    assert resolve_info_date(None, now=now) == date(2026, 6, 13)
    assert resolve_info_date("2025-01-02", now=now) == date(2025, 1, 2)
