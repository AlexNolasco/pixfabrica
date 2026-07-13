"""Pure-math easing functions for transitions."""

from __future__ import annotations

from enum import StrEnum


class EasingType(StrEnum):
    LINEAR = "linear"
    EASE_IN = "ease_in"
    EASE_OUT = "ease_out"
    EASE_IN_OUT = "ease_in_out"


def ease_in(t: float) -> float:
    return t * t


def ease_out(t: float) -> float:
    return 1.0 - (1.0 - t) ** 2


def ease_in_out(t: float) -> float:
    return 2.0 * t * t if t < 0.5 else 1.0 - (-2.0 * t + 2.0) ** 2 / 2.0


def apply_easing(easing: EasingType | str, t: float) -> float:
    t = max(0.0, min(1.0, t))
    match easing:
        case EasingType.EASE_IN | "ease_in":
            return ease_in(t)
        case EasingType.EASE_OUT | "ease_out":
            return ease_out(t)
        case EasingType.EASE_IN_OUT | "ease_in_out":
            return ease_in_out(t)
        case _:
            return t
