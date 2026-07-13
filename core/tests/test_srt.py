import pytest

from pixfabrica_core.lyrics.srt import parse_srt

# ── Basic parsing ─────────────────────────────────────────────────────────────


_BASIC = """\
1
00:00:01,000 --> 00:00:04,000
Hello world

2
00:00:05,000 --> 00:00:08,500
Goodbye
"""


def test_basic_segment_count():
    segs = parse_srt(_BASIC)
    assert len(segs) == 2


def test_basic_segment_fields():
    seg = parse_srt(_BASIC)[0]
    assert seg.index == 1
    assert seg.start == pytest.approx(1.0)
    assert seg.end == pytest.approx(4.0)
    assert seg.text == "Hello world"
    assert seg.words == ()
    assert seg.narrator is None
    assert seg.emotions == ()


def test_basic_second_segment():
    seg = parse_srt(_BASIC)[1]
    assert seg.index == 2
    assert seg.start == pytest.approx(5.0)
    assert seg.end == pytest.approx(8.5)
    assert seg.text == "Goodbye"


# ── Timestamp edge cases ──────────────────────────────────────────────────────


def test_timestamp_hours():
    srt = "1\n01:02:03,456 --> 01:02:07,000\nLate\n"
    seg = parse_srt(srt)[0]
    assert seg.start == pytest.approx(3723.456)
    assert seg.end == pytest.approx(3727.0)


def test_timestamp_dot_separator():
    # Some encoders use '.' instead of ',' for milliseconds
    srt = "1\n00:00:01.500 --> 00:00:03.000\nDot sep\n"
    seg = parse_srt(srt)[0]
    assert seg.start == pytest.approx(1.5)
    assert seg.end == pytest.approx(3.0)


# ── HTML tag stripping ────────────────────────────────────────────────────────


def test_html_tags_stripped():
    srt = "1\n00:00:00,000 --> 00:00:02,000\n<b>Bold</b> and <i>italic</i>\n"
    seg = parse_srt(srt)[0]
    assert seg.text == "Bold and italic"


def test_font_tags_stripped():
    srt = '1\n00:00:00,000 --> 00:00:02,000\n<font color="#ff0000">Red text</font>\n'
    seg = parse_srt(srt)[0]
    assert seg.text == "Red text"


# ── BOM and CRLF handling ─────────────────────────────────────────────────────


def test_bom_stripped():
    srt = "\ufeff1\n00:00:01,000 --> 00:00:02,000\nHi\n"
    segs = parse_srt(srt)
    assert len(segs) == 1
    assert segs[0].text == "Hi"


def test_crlf_normalized():
    srt = "1\r\n00:00:01,000 --> 00:00:02,000\r\nHi\r\n"
    segs = parse_srt(srt)
    assert segs[0].text == "Hi"


# ── Multi-line cue text ───────────────────────────────────────────────────────


def test_multi_line_text():
    srt = "1\n00:00:00,000 --> 00:00:03,000\nLine one\nLine two\n"
    seg = parse_srt(srt)[0]
    assert seg.text == "Line one\nLine two"


# ── Index re-sequencing ───────────────────────────────────────────────────────


def test_index_always_sequential():
    # SRT files in the wild sometimes have wrong cue numbers
    srt = "99\n00:00:00,000 --> 00:00:01,000\nFirst\n\n5\n00:00:02,000 --> 00:00:03,000\nSecond\n"
    segs = parse_srt(srt)
    assert segs[0].index == 1
    assert segs[1].index == 2


# ── Edge cases ────────────────────────────────────────────────────────────────


def test_empty_string():
    assert parse_srt("") == []


def test_no_trailing_newline():
    srt = "1\n00:00:00,000 --> 00:00:01,000\nNo newline"
    segs = parse_srt(srt)
    assert len(segs) == 1
    assert segs[0].text == "No newline"


def test_skips_blank_only_cues():
    srt = "1\n00:00:00,000 --> 00:00:01,000\n   \n\n2\n00:00:02,000 --> 00:00:03,000\nReal\n"
    segs = parse_srt(srt)
    assert len(segs) == 1
    assert segs[0].text == "Real"
