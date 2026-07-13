import pytest

from pixfabrica_core.lyrics.lrc import _LAST_LINE_DURATION, parse_lrc

# ── Basic parsing ─────────────────────────────────────────────────────────────


_BASIC = """\
[ar:Artist]
[ti:Title]

[00:12.34]Hello world
[00:17.20]Goodbye
"""


def test_basic_segment_count():
    segs = parse_lrc(_BASIC)
    assert len(segs) == 2


def test_basic_segment_fields():
    seg = parse_lrc(_BASIC)[0]
    assert seg.index == 1
    assert seg.start == pytest.approx(12.34)
    assert seg.end == pytest.approx(17.20)
    assert seg.text == "Hello world"
    assert seg.words == ()
    assert seg.narrator is None
    assert seg.emotions == ()


def test_last_line_end_time():
    seg = parse_lrc(_BASIC)[-1]
    assert seg.end == pytest.approx(seg.start + _LAST_LINE_DURATION)


# ── Timestamp precision ───────────────────────────────────────────────────────


def test_two_digit_centiseconds():
    lrc = "[00:01.50]Line\n[00:03.00]End\n"
    seg = parse_lrc(lrc)[0]
    assert seg.start == pytest.approx(1.5)


def test_three_digit_milliseconds():
    lrc = "[00:01.500]Line\n[00:03.000]End\n"
    seg = parse_lrc(lrc)[0]
    assert seg.start == pytest.approx(1.5)


def test_minutes_carry():
    lrc = "[01:30.00]Long\n[01:35.00]End\n"
    seg = parse_lrc(lrc)[0]
    assert seg.start == pytest.approx(90.0)


# ── Metadata ignored (no crash) ───────────────────────────────────────────────


def test_metadata_does_not_produce_segments():
    lrc = "[ar:Someone]\n[ti:Song]\n[al:Album]\n[by:Me]\n[00:01.00]Hi\n"
    segs = parse_lrc(lrc)
    assert len(segs) == 1
    assert segs[0].text == "Hi"


# ── Offset ────────────────────────────────────────────────────────────────────


def test_offset_positive_shifts_forward():
    lrc = "[offset:500]\n[00:01.000]Hi\n[00:03.000]Bye\n"
    segs = parse_lrc(lrc)
    assert segs[0].start == pytest.approx(1.5)


def test_offset_negative_shifts_back():
    lrc = "[offset:-200]\n[00:01.000]Hi\n[00:03.000]Bye\n"
    segs = parse_lrc(lrc)
    assert segs[0].start == pytest.approx(0.8)


def test_offset_clamps_to_zero():
    lrc = "[offset:-99999]\n[00:01.000]Hi\n"
    segs = parse_lrc(lrc)
    assert segs[0].start == 0.0


# ── Multiple timestamps per line ──────────────────────────────────────────────


def test_multiple_timestamps_expand_segments():
    lrc = "[00:10.00][00:30.00]Chorus line\n[00:50.00]Next\n"
    segs = parse_lrc(lrc)
    assert len(segs) == 3
    texts = [s.text for s in segs]
    assert texts.count("Chorus line") == 2


def test_multiple_timestamps_sorted_by_time():
    lrc = "[00:30.00][00:10.00]Repeat\n[00:50.00]End\n"
    segs = parse_lrc(lrc)
    assert segs[0].start == pytest.approx(10.0)
    assert segs[1].start == pytest.approx(30.0)


# ── Enhanced LRC word-level timestamps ───────────────────────────────────────


_ENHANCED = "[00:10.00]<00:10.00>Hello <00:10.50>world <00:11.00>foo\n[00:15.00]Next\n"


def test_enhanced_word_count():
    seg = parse_lrc(_ENHANCED)[0]
    assert len(seg.words) == 3


def test_enhanced_word_fields():
    seg = parse_lrc(_ENHANCED)[0]
    assert seg.words[0].word == "Hello"
    assert seg.words[0].start == pytest.approx(10.0)
    assert seg.words[0].end == pytest.approx(10.5)
    assert seg.words[1].word == "world"
    assert seg.words[2].word == "foo"
    assert seg.words[2].end == pytest.approx(15.0)  # falls back to seg end


def test_enhanced_clean_text():
    seg = parse_lrc(_ENHANCED)[0]
    assert seg.text == "Hello world foo"


# ── BOM and CRLF ─────────────────────────────────────────────────────────────


def test_bom_stripped():
    lrc = "\ufeff[00:01.00]Hi\n[00:03.00]Bye\n"
    segs = parse_lrc(lrc)
    assert len(segs) == 2
    assert segs[0].text == "Hi"


def test_crlf_normalized():
    lrc = "[00:01.00]Hi\r\n[00:03.00]Bye\r\n"
    segs = parse_lrc(lrc)
    assert segs[0].text == "Hi"


# ── Edge cases ────────────────────────────────────────────────────────────────


def test_empty_string():
    assert parse_lrc("") == []


def test_metadata_only():
    assert parse_lrc("[ar:No lyrics]\n[ti:Song]\n") == []


def test_sequential_index():
    lrc = "[00:01.00]A\n[00:02.00]B\n[00:03.00]C\n"
    segs = parse_lrc(lrc)
    assert [s.index for s in segs] == [1, 2, 3]
