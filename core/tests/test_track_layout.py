"""Track layout band computation."""

from pixfabrica_core.composition.track import HorizontalLayout, VerticalLayout
from pixfabrica_core.graphics import Rect


def test_vertical_equal_bands_when_header_fraction_unset() -> None:
    track = Rect(0, 0, 100, 200)
    rects = VerticalLayout().compute(track, 3)
    assert len(rects) == 3
    assert rects[0] == Rect(0, 0, 100, 200 / 3)
    assert rects[1].y == 200 / 3
    assert rects[2].y == 2 * 200 / 3


def test_vertical_weighted_two_band() -> None:
    track = Rect(0, 0, 100, 200)
    rects = VerticalLayout(header_fraction=0.2).compute(track, 2)
    assert rects[0] == Rect(0, 0, 100, 40)
    assert rects[1] == Rect(0, 40, 100, 160)


def test_vertical_header_fraction_ignored_when_not_two_clips() -> None:
    track = Rect(0, 0, 100, 300)
    rects = VerticalLayout(header_fraction=0.2).compute(track, 3)
    assert rects[0].height == 100
    assert rects[1].height == 100
    assert rects[2].height == 100


def test_horizontal_weighted_two_band() -> None:
    track = Rect(0, 0, 200, 100)
    rects = HorizontalLayout(header_fraction=0.2).compute(track, 2)
    assert rects[0] == Rect(0, 0, 40, 100)
    assert rects[1] == Rect(40, 0, 160, 100)


def test_horizontal_equal_bands_when_header_fraction_unset() -> None:
    track = Rect(0, 0, 200, 100)
    rects = HorizontalLayout().compute(track, 2)
    assert rects[0] == Rect(0, 0, 100, 100)
    assert rects[1] == Rect(100, 0, 100, 100)
