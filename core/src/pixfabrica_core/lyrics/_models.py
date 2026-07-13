from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CaptionWord:
    start: float
    end: float
    word: str
    score: float | None = None


@dataclass(frozen=True)
class CaptionSegment:
    index: int
    start: float
    end: float
    text: str
    words: tuple[CaptionWord, ...] = field(default_factory=tuple)
    narrator: str | None = None
    emotions: tuple[str, ...] = field(default_factory=tuple)
