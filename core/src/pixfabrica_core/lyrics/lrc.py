from __future__ import annotations

import contextlib
import re

from pixfabrica_core.lyrics._models import CaptionSegment, CaptionWord

# [MM:SS.xx] or [MM:SS.xxx]
_LINE_TS_RE = re.compile(r"\[(\d+):(\d{2})\.(\d{2,3})\]")
# <MM:SS.xx> or <MM:SS.xxx> — Enhanced LRC word-level
_WORD_TS_RE = re.compile(r"<(\d+):(\d{2})\.(\d{2,3})>")
# Metadata tags: [ar:...], [ti:...], [offset:...]
_META_RE = re.compile(r"^\[([a-zA-Z#]+):([^\]]*)\]$")

_LAST_LINE_DURATION = 5.0


def _ts(mm: str, ss: str, frac: str) -> float:
    ms = int(frac.ljust(3, "0")[:3])
    return int(mm) * 60 + int(ss) + ms / 1000


def _extract_words(text: str, seg_start: float, seg_end: float) -> tuple[CaptionWord, ...]:
    matches = list(_WORD_TS_RE.finditer(text))
    if not matches:
        return ()

    words: list[CaptionWord] = []
    for i, m in enumerate(matches):
        word_start = _ts(m.group(1), m.group(2), m.group(3))
        next_m = matches[i + 1] if i + 1 < len(matches) else None
        word_end = _ts(next_m.group(1), next_m.group(2), next_m.group(3)) if next_m else seg_end

        chunk_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunk = text[m.end() : chunk_end].strip()

        if chunk:
            words.append(CaptionWord(start=word_start, end=word_end, word=chunk))

    return tuple(words)


def parse_lrc(text: str) -> list[CaptionSegment]:
    raw = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    raw = raw.lstrip("\ufeff")

    offset_ms = 0.0
    # Raw entries before end-time assignment: (start, lyric_text)
    entries: list[tuple[float, str]] = []

    for line in raw.split("\n"):
        line = line.strip()
        if not line:
            continue

        # Metadata
        meta = _META_RE.match(line)
        if meta:
            key = meta.group(1).lower()
            if key == "offset":
                with contextlib.suppress(ValueError):
                    offset_ms = float(meta.group(2).strip())
            continue

        # Lyric line — may have multiple leading timestamps
        timestamps: list[float] = []
        rest = line
        while True:
            m = _LINE_TS_RE.match(rest)
            if not m:
                break
            timestamps.append(_ts(m.group(1), m.group(2), m.group(3)))
            rest = rest[m.end() :]

        if not timestamps:
            continue

        for ts in timestamps:
            entries.append((ts, rest))

    if not entries:
        return []

    # Apply offset (positive = shift forward, negative = shift back)
    offset_s = offset_ms / 1000.0
    entries = [(max(0.0, t + offset_s), txt) for t, txt in entries]
    entries.sort(key=lambda e: e[0])

    segments: list[CaptionSegment] = []
    for i, (start, lyric_text) in enumerate(entries):
        end = entries[i + 1][0] if i + 1 < len(entries) else start + _LAST_LINE_DURATION
        words = _extract_words(lyric_text, start, end)
        # Strip word-level tags for clean text
        clean = _WORD_TS_RE.sub("", lyric_text).strip()

        if clean or words:
            segments.append(
                CaptionSegment(
                    index=i + 1,
                    start=start,
                    end=end,
                    text=clean,
                    words=words,
                )
            )

    return segments
