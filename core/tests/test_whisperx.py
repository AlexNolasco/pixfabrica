import json

import pytest

from pixfabrica_core.lyrics.whisperx import parse_whisperx

_BASIC = {
    "segments": [
        {
            "line": 1,
            "start": 0.0,
            "end": 6.979,
            "text": "Otra vez",
            "narrator": "speaker_0",
            "emotions": None,
        },
        {
            "line": 2,
            "start": 7.0,
            "end": 10.5,
            "text": "Hello world",
        },
    ],
    "words": [
        {"word": "Otra", "start": 0.2, "end": 0.8, "score": 0.95},
        {"word": "vez", "start": 0.9, "end": 1.4, "score": 0.88},
        {"word": "Hello", "start": 7.1, "end": 7.5, "score": 0.92},
        {"word": "world", "start": 7.6, "end": 8.0, "score": 0.90},
    ],
}


# ── Basic parsing ─────────────────────────────────────────────────────────────


def test_basic_segment_count():
    segs = parse_whisperx(_BASIC)
    assert len(segs) == 2


def test_basic_segment_fields():
    seg = parse_whisperx(_BASIC)[0]
    assert seg.index == 1
    assert seg.start == pytest.approx(0.0)
    assert seg.end == pytest.approx(6.979)
    assert seg.text == "Otra vez"
    assert seg.narrator == "speaker_0"
    assert seg.emotions == ()


# ── Word matching by time ─────────────────────────────────────────────────────


def test_words_matched_to_first_segment():
    segs = parse_whisperx(_BASIC)
    assert len(segs[0].words) == 2
    assert segs[0].words[0].word == "Otra"
    assert segs[0].words[1].word == "vez"


def test_words_matched_to_second_segment():
    segs = parse_whisperx(_BASIC)
    assert len(segs[1].words) == 2
    assert segs[1].words[0].word == "Hello"
    assert segs[1].words[1].word == "world"


def test_word_fields():
    word = parse_whisperx(_BASIC)[0].words[0]
    assert word.start == pytest.approx(0.2)
    assert word.end == pytest.approx(0.8)
    assert word.score == pytest.approx(0.95)


def test_word_at_seg_end_excluded():
    # word.start == seg.end should NOT be included in that segment
    data = {
        "segments": [
            {"start": 0.0, "end": 2.0, "text": "A"},
            {"start": 2.0, "end": 4.0, "text": "B"},
        ],
        "words": [{"word": "boundary", "start": 2.0, "end": 2.5}],
    }
    segs = parse_whisperx(data)
    assert segs[0].words == ()
    assert segs[1].words[0].word == "boundary"


def test_orphan_words_dropped():
    # Word with no matching segment (outside all segment ranges)
    data = {
        "segments": [{"start": 0.0, "end": 1.0, "text": "Hi"}],
        "words": [{"word": "ghost", "start": 5.0, "end": 5.5}],
    }
    assert parse_whisperx(data)[0].words == ()


# ── Narrator / speaker ────────────────────────────────────────────────────────


def test_narrator_field():
    data = {"segments": [{"start": 0.0, "end": 1.0, "text": "Hi", "narrator": "Alice"}]}
    assert parse_whisperx(data)[0].narrator == "Alice"


def test_speaker_field_fallback():
    data = {"segments": [{"start": 0.0, "end": 1.0, "text": "Hi", "speaker": "SPEAKER_01"}]}
    assert parse_whisperx(data)[0].narrator == "SPEAKER_01"


def test_narrator_takes_precedence_over_speaker():
    data = {
        "segments": [
            {"start": 0.0, "end": 1.0, "text": "Hi", "narrator": "Alice", "speaker": "SPEAKER_01"}
        ]
    }
    assert parse_whisperx(data)[0].narrator == "Alice"


# ── Emotions ──────────────────────────────────────────────────────────────────


def test_emotions_list():
    data = {
        "segments": [{"start": 0.0, "end": 1.0, "text": "Hi", "emotions": ["happy", "excited"]}]
    }
    assert parse_whisperx(data)[0].emotions == ("happy", "excited")


def test_emotions_null_becomes_empty():
    data = {"segments": [{"start": 0.0, "end": 1.0, "text": "Hi", "emotions": None}]}
    assert parse_whisperx(data)[0].emotions == ()


# ── line → index ──────────────────────────────────────────────────────────────


def test_line_field_used_as_index():
    data = {"segments": [{"line": 42, "start": 0.0, "end": 1.0, "text": "Hi"}]}
    assert parse_whisperx(data)[0].index == 42


def test_index_auto_assigned_when_no_line():
    data = {
        "segments": [
            {"start": 0.0, "end": 1.0, "text": "A"},
            {"start": 1.0, "end": 2.0, "text": "B"},
        ]
    }
    segs = parse_whisperx(data)
    assert segs[0].index == 1
    assert segs[1].index == 2


# ── JSON string input ─────────────────────────────────────────────────────────


def test_accepts_json_string():
    segs = parse_whisperx(json.dumps(_BASIC))
    assert len(segs) == 2
    assert segs[0].text == "Otra vez"


# ── Robustness ────────────────────────────────────────────────────────────────


def test_empty_segments():
    assert parse_whisperx({"segments": []}) == []


def test_missing_segments_key():
    assert parse_whisperx({}) == []


def test_no_words_key():
    data = {"segments": [{"start": 0.0, "end": 1.0, "text": "Hi"}]}
    segs = parse_whisperx(data)
    assert segs[0].words == ()


def test_segment_missing_timestamps_skipped():
    data = {"segments": [{"text": "No times"}]}
    assert parse_whisperx(data) == []


def test_word_missing_timestamps_skipped():
    data = {
        "segments": [{"start": 0.0, "end": 2.0, "text": "Hi"}],
        "words": [{"word": "Hi"}],
    }
    assert parse_whisperx(data)[0].words == ()
