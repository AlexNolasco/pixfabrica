from __future__ import annotations

import json
from typing import Any

from pixfabrica_core.lyrics._models import CaptionSegment, CaptionWord


def _parse_word(raw: dict[str, Any]) -> CaptionWord | None:
    word = (raw.get("word") or "").strip()
    if not word:
        return None
    start = raw.get("start")
    end = raw.get("end")
    if start is None or end is None:
        return None
    return CaptionWord(
        start=float(start),
        end=float(end),
        word=word,
        score=float(raw["score"]) if raw.get("score") is not None else None,
    )


def parse_whisperx(source: str | dict[str, Any]) -> list[CaptionSegment]:
    data: dict[str, Any] = json.loads(source) if isinstance(source, str) else source

    raw_words: list[CaptionWord] = []
    for r in data.get("words") or []:
        w = _parse_word(r)
        if w is not None:
            raw_words.append(w)

    segments: list[CaptionSegment] = []
    for i, raw in enumerate(data.get("segments") or [], start=1):
        text = (raw.get("text") or "").strip()
        start = raw.get("start")
        end = raw.get("end")
        if start is None or end is None:
            continue

        seg_start, seg_end = float(start), float(end)

        # Words whose start time falls within [seg_start, seg_end)
        words = tuple(w for w in raw_words if seg_start <= w.start < seg_end)

        narrator: str | None = raw.get("narrator") or raw.get("speaker") or None

        raw_emotions = raw.get("emotions")
        emotions: tuple[str, ...] = (
            tuple(e for e in raw_emotions if e) if isinstance(raw_emotions, list) else ()
        )

        segments.append(
            CaptionSegment(
                index=raw.get("line", i),
                start=seg_start,
                end=seg_end,
                text=text,
                words=words,
                narrator=narrator,
                emotions=emotions,
            )
        )

    return segments
