from __future__ import annotations

import re

from pixfabrica_core.lyrics._models import CaptionSegment

_ANY_TAG_RE = re.compile(r"<[^>]+>")
# SRT timestamps: HH:MM:SS,mmm
_TIMELINE_RE = re.compile(
    r"(\d+):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d+):(\d{2}):(\d{2})[,.](\d{3})"
)


def _parse_timestamp(hh: str, mm: str, ss: str, ms: str) -> float:
    return int(hh) * 3600 + int(mm) * 60 + int(ss) + int(ms) / 1000


def parse_srt(text: str) -> list[CaptionSegment]:
    raw = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    raw = raw.lstrip("\ufeff")
    lines = raw.split("\n")

    segments: list[CaptionSegment] = []
    index = 1
    i = 0

    while i < len(lines):
        if not lines[i].strip():
            i += 1
            continue

        # Cue index line (required in SRT, but we skip gracefully if absent)
        m = _TIMELINE_RE.search(lines[i])
        if not m and lines[i].strip().isdigit():
            i += 1
            if i >= len(lines):
                break
            m = _TIMELINE_RE.search(lines[i])

        if not m:
            i += 1
            continue

        start = _parse_timestamp(m.group(1), m.group(2), m.group(3), m.group(4))
        end = _parse_timestamp(m.group(5), m.group(6), m.group(7), m.group(8))
        i += 1

        text_lines: list[str] = []
        while i < len(lines) and lines[i].strip():
            text_lines.append(lines[i])
            i += 1

        raw_text = "\n".join(text_lines)
        clean = _ANY_TAG_RE.sub("", raw_text).strip()

        if clean:
            segments.append(
                CaptionSegment(
                    index=index,
                    start=start,
                    end=end,
                    text=clean,
                )
            )
            index += 1

    return segments
