"""Locale-aware formatting for std-info-track-card metadata and stats."""

from __future__ import annotations

from datetime import UTC, date, datetime

_MONTHS_EN = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)
_MONTHS_ES = (
    "ene",
    "feb",
    "mar",
    "abr",
    "may",
    "jun",
    "jul",
    "ago",
    "sep",
    "oct",
    "nov",
    "dic",
)


def _normalize_locale(locale: str) -> str:
    return locale.lower().replace("_", "-")


def format_grouped_count(value: int, locale: str) -> str:
    """Format an exact integer with locale-appropriate grouping."""
    negative = value < 0
    n = abs(int(value))
    grouped = f"{n:,}".replace(",", ".") if _normalize_locale(locale).startswith("es") else f"{n:,}"
    return f"-{grouped}" if negative else grouped


def format_play_count(value: int, locale: str) -> str:
    """Abbreviate play counts at >= 10_000; otherwise exact grouped."""
    n = max(0, int(value))
    if n >= 1_000_000:
        scaled = n / 1_000_000
        if scaled >= 100:
            return f"{int(scaled)}M"
        text = f"{scaled:.1f}".rstrip("0").rstrip(".")
        return f"{text}M"
    if n >= 10_000:
        scaled = n / 1_000
        if scaled >= 100:
            return f"{int(scaled)}K"
        text = f"{scaled:.1f}".rstrip("0").rstrip(".")
        return f"{text}K"
    return format_grouped_count(n, locale)


def format_duration(seconds: float) -> str:
    """Render duration as m:ss or h:mm:ss when >= 1 hour."""
    total = max(0, int(round(seconds)))
    hours = total // 3600
    minutes = (total % 3600) // 60
    secs = total % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def resolve_info_date(value: str | None, *, now: datetime | None = None) -> date:
    if value:
        return date.fromisoformat(value)
    instant = now or datetime.now(UTC)
    return instant.date()


def format_medium_date(value: date, locale: str) -> str:
    """Medium localized date (e.g. Jun 13, 2026 in en)."""
    loc = _normalize_locale(locale)
    if loc.startswith("zh"):
        return f"{value.year}年{value.month}月{value.day}日"
    if loc.startswith("ja"):
        return f"{value.year}年{value.month}月{value.day}日"
    if loc.startswith("es"):
        month = _MONTHS_ES[value.month - 1]
        return f"{value.day} {month} {value.year}"
    month = _MONTHS_EN[value.month - 1]
    return f"{month} {value.day}, {value.year}"
