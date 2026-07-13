from __future__ import annotations

import re

from pixfabrica_core.lyrics._models import CaptionSegment, CaptionWord

# Matches inline word-level timestamps: <00:01.234> or <00:01:23.456>
_INLINE_TS_RE = re.compile(r"<(\d+:\d{2}(?::\d{2})?(?:\.\d+)?)>")
_ANY_TAG_RE = re.compile(r"<[^>]+>")


def _parse_timestamp(ts: str) -> float:
    parts = ts.split(":")
    if len(parts) == 2:
        mm, ss_ms = parts
        ss, ms = (ss_ms.split(".") + ["0"])[:2]
        return int(mm) * 60 + int(ss) + int(ms.ljust(3, "0")[:3]) / 1000
    if len(parts) == 3:
        hh, mm, ss_ms = parts
        ss, ms = (ss_ms.split(".") + ["0"])[:2]
        return int(hh) * 3600 + int(mm) * 60 + int(ss) + int(ms.ljust(3, "0")[:3]) / 1000
    raise ValueError(f"Invalid VTT timestamp: {ts!r}")


def _extract_narrator(lines: list[str]) -> tuple[str | None, str]:
    joined = "\n".join(lines)
    m = re.match(r"^\s*<v\s+([^>]+)>([\s\S]*)$", joined, re.IGNORECASE)
    if m:
        narrator = m.group(1).strip()
        payload = re.sub(r"</v>\s*$", "", m.group(2), flags=re.IGNORECASE).strip()
        return narrator, payload
    m = re.match(r"^\s*<v>([\s\S]*)$", joined, re.IGNORECASE)
    if m:
        payload = re.sub(r"</v>\s*$", "", m.group(1), flags=re.IGNORECASE).strip()
        return None, payload
    return None, joined


def _extract_emotions(text: str) -> tuple[str, tuple[str, ...]]:
    emotions: list[str] = []

    def _collect(m: re.Match[str]) -> str:
        v = m.group(1).strip()
        if v:
            emotions.append(v)
        return ""

    cleaned = re.sub(r"\[([^\]\n]+)\]", _collect, text)
    cleaned = re.sub(r"[ \t\f\v]+", " ", cleaned).strip()
    unique = tuple(dict.fromkeys(e for e in emotions if e))
    return cleaned, unique


def _extract_words(text: str, seg_start: float, seg_end: float) -> tuple[CaptionWord, ...]:
    matches = list(_INLINE_TS_RE.finditer(text))
    if not matches:
        return ()

    words: list[CaptionWord] = []
    for i, m in enumerate(matches):
        word_start = _parse_timestamp(m.group(1))
        word_end = _parse_timestamp(matches[i + 1].group(1)) if i + 1 < len(matches) else seg_end

        chunk_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunk = _ANY_TAG_RE.sub("", text[m.end() : chunk_end]).strip()

        if chunk:
            words.append(CaptionWord(start=word_start, end=word_end, word=chunk))

    return tuple(words)


def parse_vtt(text: str) -> list[CaptionSegment]:
    raw = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    # Strip BOM
    raw = raw.lstrip("\ufeff")
    lines = raw.split("\n")

    i = 0
    # Skip WEBVTT header block
    if re.match(r"^WEBVTT(?:\s|$)", lines[0], re.IGNORECASE):
        i += 1
        while i < len(lines) and lines[i].strip():
            i += 1
        while i < len(lines) and not lines[i].strip():
            i += 1

    def _is_note(s: str) -> bool:
        return bool(re.match(r"^NOTE($|\s)", s.strip(), re.IGNORECASE))

    def _is_timeline(s: str) -> bool:
        return "-->" in s

    segments: list[CaptionSegment] = []
    index = 1

    while i < len(lines):
        if not lines[i].strip():
            i += 1
            continue

        if _is_note(lines[i]):
            i += 1
            while i < len(lines) and lines[i].strip():
                i += 1
            continue

        # Optional cue identifier
        time_i = i if _is_timeline(lines[i]) else i + 1

        if time_i >= len(lines) or not _is_timeline(lines[time_i]):
            while i < len(lines) and lines[i].strip():
                i += 1
            continue

        timeline = lines[time_i].strip()
        lhs, rhs_plus = timeline.split("-->", 1)
        start = _parse_timestamp(lhs.strip())
        end = _parse_timestamp(rhs_plus.strip().split()[0])

        text_lines: list[str] = []
        i = time_i + 1
        while i < len(lines) and lines[i].strip() and not _is_note(lines[i]):
            text_lines.append(lines[i])
            i += 1

        narrator, payload = _extract_narrator(text_lines)
        words = _extract_words(payload, start, end)
        # Strip inline timestamps and remaining tags before emotion extraction
        clean = _INLINE_TS_RE.sub("", payload)
        clean = _ANY_TAG_RE.sub("", clean).strip()
        clean, emotions = _extract_emotions(clean)

        segments.append(
            CaptionSegment(
                index=index,
                start=start,
                end=end,
                text=clean,
                words=words,
                narrator=narrator,
                emotions=emotions,
            )
        )
        index += 1

    return segments
