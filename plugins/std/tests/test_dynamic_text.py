"""Tests for std-dynamic-text entry effects."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from pixfabrica_core.clips import JobInfo, RenderContext, TimeState
from pixfabrica_core.graphics import Rect
from pixfabrica_core.theme.color import ColorPalette
from pixfabrica_core.theme.typography import FontPalette
from pixfabrica_std.text.dynamic_text import DynamicText
from pixfabrica_std.text.skia_font import make_typography_font

FPS = 30.0


def _font():
    return make_typography_font(FontPalette().body_medium)


def _draw(t: float = 0.0, frame: int | None = None, **clip_kwargs: Any) -> MagicMock:
    bounds = Rect(0, 0, 800, 600)
    canvas = MagicMock()
    job = JobInfo(
        title="t",
        description="d",
        width=int(bounds.width),
        height=int(bounds.height),
        fps=FPS,
        duration=10.0,
        colors=ColorPalette(),
        typography=FontPalette(),
        locale="en",
    )
    ctx = RenderContext(
        job=job,
        time=TimeState(frame=int(t * FPS) if frame is None else frame, t=t),
        bounds=bounds,
        canvas=canvas,
    )
    DynamicText(id="test", **clip_kwargs).draw(ctx)
    return canvas


def _draw_xs(canvas: MagicMock) -> list[float]:
    return [c.args[1] for c in canvas.drawString.call_args_list]


def _draw_texts(canvas: MagicMock) -> list[str]:
    return [c.args[0] for c in canvas.drawString.call_args_list]


# ----------------------------------------------------------------- spread


def test_spread_starts_at_normal_spacing() -> None:
    font = _font()
    canvas = _draw(t=0.0, text="AB", effect="spread", spread=0.5)
    xs = _draw_xs(canvas)
    assert len(xs) == 2
    assert xs[1] - xs[0] == pytest.approx(font.measureText("A"))


def test_spread_reaches_full_gap_and_holds() -> None:
    font = _font()
    expected_gap = font.measureText("A") + 0.5 * font.getSize()
    # duration=5.0 → settle = min(0.3 * 5.0, 1.5) = 1.5s
    for t in (1.5, 5.0):  # settle time and well into the hold
        xs = _draw_xs(_draw(t=t, text="AB", effect="spread", spread=0.5, duration=5.0))
        assert xs[1] - xs[0] == pytest.approx(expected_gap)


def test_spread_settle_scales_with_short_durations() -> None:
    font = _font()
    expected_gap = font.measureText("A") + 0.5 * font.getSize()
    # duration=2.0 → settle = 0.3 * 2.0 = 0.6s
    xs = _draw_xs(_draw(t=0.6, text="AB", effect="spread", spread=0.5, duration=2.0))
    assert xs[1] - xs[0] == pytest.approx(expected_gap)


def test_spread_settle_caps_for_long_durations() -> None:
    font = _font()
    expected_gap = font.measureText("A") + 0.5 * font.getSize()
    # duration=50 → settle capped at 1.5s: still animating at t=1.0, settled at t=1.5
    xs_mid = _draw_xs(_draw(t=1.0, text="AB", effect="spread", spread=0.5, duration=50.0))
    assert xs_mid[1] - xs_mid[0] < expected_gap
    xs_done = _draw_xs(_draw(t=1.5, text="AB", effect="spread", spread=0.5, duration=50.0))
    assert xs_done[1] - xs_done[0] == pytest.approx(expected_gap)


def test_spread_block_stays_centered() -> None:
    font = _font()
    w_b = font.measureText("B")
    for t in (0.0, 0.4, 2.0):
        xs = _draw_xs(_draw(t=t, text="AB", effect="spread"))
        block_center = (xs[0] + xs[1] + w_b) / 2.0
        assert block_center == pytest.approx(400.0)


def test_spread_animates_letters_within_a_single_word() -> None:
    xs_start = _draw_xs(_draw(t=0.0, text="Hello", effect="spread"))
    xs_end = _draw_xs(_draw(t=5.0, text="Hello", effect="spread"))
    assert len(xs_start) == 5
    assert xs_end[1] - xs_end[0] > xs_start[1] - xs_start[0]


def test_spread_skips_spaces_but_keeps_their_advance() -> None:
    font = _font()
    canvas = _draw(t=0.0, text="A B", effect="spread")
    assert _draw_texts(canvas) == ["A", "B"]
    xs = _draw_xs(canvas)
    assert xs[1] - xs[0] == pytest.approx(font.measureText("A") + font.measureText(" "))


def test_spread_uses_clip_local_time() -> None:
    xs_global = _draw_xs(_draw(t=2.0, text="AB CD", effect="spread", start=2.0))
    xs_zero = _draw_xs(_draw(t=0.0, text="AB CD", effect="spread"))
    assert xs_global == xs_zero


# -------------------------------------------------------------- typewriter


def test_typewriter_reveals_at_constant_rate() -> None:
    canvas = _draw(t=0.25, text="Hello", effect="typewriter", type_speed=10.0)
    assert _draw_texts(canvas) == ["He"]


def test_typewriter_full_text_after_done() -> None:
    canvas = _draw(t=5.0, text="Hello", effect="typewriter", type_speed=10.0)
    assert _draw_texts(canvas) == ["Hello"]


def test_typewriter_cursor_solid_while_typing() -> None:
    canvas = _draw(t=0.25, text="Hello", effect="typewriter", type_speed=10.0)
    canvas.drawRect.assert_called_once()


def test_typewriter_cursor_hides_after_linger() -> None:
    # done_t = 0.5s, linger = 1.0s; at t=2.0 the cursor must be gone
    canvas = _draw(t=2.0, text="Hello", effect="typewriter", type_speed=10.0)
    canvas.drawRect.assert_not_called()


def test_typewriter_cursor_disabled() -> None:
    canvas = _draw(t=0.25, text="Hello", effect="typewriter", type_speed=10.0, cursor=False)
    canvas.drawRect.assert_not_called()


def test_typewriter_multiline_streams_across_lines() -> None:
    canvas = _draw(t=0.7, text="AB\nCD", effect="typewriter", type_speed=10.0)
    assert _draw_texts(canvas) == ["AB", "CD"]
    ys = [c.args[2] for c in canvas.drawString.call_args_list]
    assert ys[1] > ys[0]


# ---------------------------------------------------------------- scramble


def test_scramble_is_deterministic_per_frame() -> None:
    a = _draw_texts(_draw(t=0.0, frame=0, text="HELLO WORLD", effect="scramble"))
    b = _draw_texts(_draw(t=0.0, frame=0, text="HELLO WORLD", effect="scramble"))
    assert a == b


def test_scramble_rerolls_between_buckets() -> None:
    a = _draw_texts(_draw(t=0.0, frame=0, text="HELLO WORLD", effect="scramble"))
    b = _draw_texts(_draw(t=0.0, frame=3, text="HELLO WORLD", effect="scramble"))
    assert a != b


def test_scramble_resolves_left_to_right() -> None:
    # type_speed=10, t=0.3 → first 3 chars resolved
    texts = _draw_texts(_draw(t=0.3, text="HELLO", effect="scramble", type_speed=10.0))
    assert texts[:3] == ["H", "E", "L"]


def test_scramble_fully_resolved_after_done() -> None:
    texts = _draw_texts(_draw(t=5.0, text="HELLO WORLD", effect="scramble", type_speed=10.0))
    assert "".join(texts) == "HELLOWORLD"  # spaces are never drawn


def test_scramble_glyph_positions_stable_across_rerolls() -> None:
    xs_a = _draw_xs(_draw(t=0.0, frame=0, text="HELLO", effect="scramble"))
    xs_b = _draw_xs(_draw(t=0.0, frame=3, text="HELLO", effect="scramble"))
    assert xs_a == xs_b


# ----------------------------------------------------------------- cascade


def test_cascade_no_words_drawn_at_start() -> None:
    canvas = _draw(t=0.0, text="One Two Three", effect="cascade")
    canvas.drawString.assert_not_called()


def test_cascade_all_words_settled_at_settle_time() -> None:
    # duration=5.0 → settle = 1.5s
    canvas = _draw(t=1.5, text="One Two Three", effect="cascade", duration=5.0)
    assert _draw_texts(canvas) == ["One", "Two", "Three"]
    ys = [c.args[2] for c in canvas.drawString.call_args_list]
    assert ys[0] == ys[1] == ys[2]  # all at final baseline, no residual rise


def test_cascade_words_appear_in_reading_order() -> None:
    # settle = 1.5; stagger = 1.5 / 4 = 0.375; at t=0.4 words 0 and 1 have started, word 2 has not
    canvas = _draw(t=0.4, text="One Two Three", effect="cascade", duration=5.0)
    assert _draw_texts(canvas) == ["One", "Two"]


# ------------------------------------------------------------------ common


def test_rotation_pivots_on_anchor() -> None:
    canvas = _draw(t=0.0, text="Hi", angle=45, offset_x=0.25, offset_y=0.75)
    canvas.rotate.assert_called_once_with(45.0, 200.0, 450.0)


def test_zero_angle_skips_rotation() -> None:
    canvas = _draw(t=0.0, text="Hi", angle=0)
    canvas.rotate.assert_not_called()


def test_empty_text_draws_nothing() -> None:
    canvas = _draw(t=1.0, text="", effect="typewriter")
    canvas.drawString.assert_not_called()
    canvas.drawRect.assert_not_called()
