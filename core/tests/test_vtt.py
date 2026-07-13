import pytest

from pixfabrica_core.lyrics.vtt import _parse_timestamp, parse_vtt

# ── Timestamp parsing ─────────────────────────────────────────────────────────


def test_timestamp_mm_ss():
    assert _parse_timestamp("01:23.456") == pytest.approx(83.456)


def test_timestamp_hh_mm_ss():
    assert _parse_timestamp("01:02:03.500") == pytest.approx(3723.5)


def test_timestamp_zero():
    assert _parse_timestamp("00:00.000") == 0.0


def test_timestamp_invalid():
    with pytest.raises(ValueError, match="Invalid VTT timestamp"):
        _parse_timestamp("bad")


# ── Basic parsing ─────────────────────────────────────────────────────────────


_BASIC = """\
WEBVTT

1
00:00.500 --> 00:02.000
Hello world

2
00:03.000 --> 00:05.500
Goodbye
"""


def test_basic_segment_count():
    segs = parse_vtt(_BASIC)
    assert len(segs) == 2


def test_basic_segment_fields():
    seg = parse_vtt(_BASIC)[0]
    assert seg.index == 1
    assert seg.start == pytest.approx(0.5)
    assert seg.end == pytest.approx(2.0)
    assert seg.text == "Hello world"
    assert seg.words == ()
    assert seg.narrator is None
    assert seg.emotions == ()


def test_basic_second_segment():
    seg = parse_vtt(_BASIC)[1]
    assert seg.index == 2
    assert seg.text == "Goodbye"


# ── No cue identifiers ────────────────────────────────────────────────────────


_NO_IDS = """\
WEBVTT

00:00.000 --> 00:01.000
Line one

00:02.000 --> 00:03.000
Line two
"""


def test_no_cue_identifiers():
    segs = parse_vtt(_NO_IDS)
    assert len(segs) == 2
    assert segs[0].text == "Line one"
    assert segs[1].text == "Line two"


# ── BOM and CRLF handling ─────────────────────────────────────────────────────


def test_bom_stripped():
    vtt = "\ufeffWEBVTT\n\n00:00.000 --> 00:01.000\nHi\n"
    segs = parse_vtt(vtt)
    assert len(segs) == 1
    assert segs[0].text == "Hi"


def test_crlf_normalized():
    vtt = "WEBVTT\r\n\r\n00:00.000 --> 00:01.000\r\nHi\r\n"
    segs = parse_vtt(vtt)
    assert segs[0].text == "Hi"


# ── NOTE blocks skipped ───────────────────────────────────────────────────────


_WITH_NOTE = """\
WEBVTT

NOTE This is a comment
and it continues here

00:00.000 --> 00:01.000
Visible
"""


def test_note_blocks_skipped():
    segs = parse_vtt(_WITH_NOTE)
    assert len(segs) == 1
    assert segs[0].text == "Visible"


# ── Cue settings ignored ──────────────────────────────────────────────────────


_WITH_SETTINGS = """\
WEBVTT

00:00.000 --> 00:02.000 position:50% align:center
Centered text
"""


def test_cue_settings_ignored():
    segs = parse_vtt(_WITH_SETTINGS)
    assert segs[0].end == pytest.approx(2.0)
    assert segs[0].text == "Centered text"


# ── Narrator ──────────────────────────────────────────────────────────────────


_WITH_NARRATOR = """\
WEBVTT

00:00.000 --> 00:03.000
<v Alice>Hello there</v>
"""


def test_narrator_extracted():
    seg = parse_vtt(_WITH_NARRATOR)[0]
    assert seg.narrator == "Alice"
    assert seg.text == "Hello there"


_WITH_NARRATOR_NO_NAME = """\
WEBVTT

00:00.000 --> 00:03.000
<v>No name</v>
"""


def test_narrator_no_name():
    seg = parse_vtt(_WITH_NARRATOR_NO_NAME)[0]
    assert seg.narrator is None
    assert seg.text == "No name"


# ── Emotions / bracketed NSI ──────────────────────────────────────────────────


_WITH_EMOTIONS = """\
WEBVTT

00:00.000 --> 00:03.000
[cheerfully] Hello [softly] world
"""


def test_emotions_extracted():
    seg = parse_vtt(_WITH_EMOTIONS)[0]
    assert seg.emotions == ("cheerfully", "softly")
    assert seg.text == "Hello world"


def test_emotions_deduplicated():
    vtt = "WEBVTT\n\n00:00.000 --> 00:01.000\n[happy] Hi [happy] there\n"
    seg = parse_vtt(vtt)[0]
    assert seg.emotions == ("happy",)


# ── Word-level timestamps ─────────────────────────────────────────────────────


_WITH_WORDS = """\
WEBVTT

00:00.000 --> 00:03.000
<00:00.000>Hello <00:01.000>world <00:02.000>foo
"""


def test_word_level_timing():
    seg = parse_vtt(_WITH_WORDS)[0]
    assert len(seg.words) == 3
    assert seg.words[0].word == "Hello"
    assert seg.words[0].start == pytest.approx(0.0)
    assert seg.words[0].end == pytest.approx(1.0)
    assert seg.words[1].word == "world"
    assert seg.words[1].start == pytest.approx(1.0)
    assert seg.words[1].end == pytest.approx(2.0)
    assert seg.words[2].word == "foo"
    assert seg.words[2].start == pytest.approx(2.0)
    assert seg.words[2].end == pytest.approx(3.0)  # falls back to seg end


def test_word_level_text_still_clean():
    seg = parse_vtt(_WITH_WORDS)[0]
    assert seg.text == "Hello world foo"


# ── Word-level with <c> tags (karaoke style) ──────────────────────────────────


_WITH_C_TAGS = """\
WEBVTT

00:00.000 --> 00:04.000
<00:00.000><c>One</c> <00:01.500><c>Two</c> <00:02.500><c>Three</c>
"""


def test_word_level_c_tags_stripped():
    seg = parse_vtt(_WITH_C_TAGS)[0]
    assert len(seg.words) == 3
    assert seg.words[0].word == "One"
    assert seg.words[1].word == "Two"
    assert seg.words[2].word == "Three"


# ── Empty / edge cases ────────────────────────────────────────────────────────


def test_empty_string():
    assert parse_vtt("") == []


def test_header_only():
    assert parse_vtt("WEBVTT\n") == []


def test_multi_line_cue_text():
    vtt = "WEBVTT\n\n00:00.000 --> 00:02.000\nLine one\nLine two\n"
    seg = parse_vtt(vtt)[0]
    assert seg.text == "Line one\nLine two"
