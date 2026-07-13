"""Tests for NLS keys on Literal[...] field options."""

from __future__ import annotations

from pixfabrica_cli.commands.gen_nls import _add_literal_strings
from pixfabrica_cli.literal_schema import literal_display_en
from pixfabrica_std.background.gradient import Gradient
from pixfabrica_std.progress.progress_bar import ProgressBar


def test_literal_display_en_title_cases_clip_wire():
    assert literal_display_en("clip") == "Clip"
    assert literal_display_en("job") == "Job"


def test_literal_nls_keys_time_mode_clip_option():
    strings: dict[str, str] = {}
    _add_literal_strings(
        strings, "std-progress-bar", "time_mode", ProgressBar.model_fields["time_mode"]
    )
    assert strings["clip.std-progress-bar.field.time_mode.option.clip"] == "Clip"


def test_literal_nls_keys_gradient_direction():
    strings: dict[str, str] = {}
    _add_literal_strings(strings, "std-gradient", "direction", Gradient.model_fields["direction"])
    assert strings["clip.std-gradient.field.direction.option.to_bottom"] == "To Bottom"
    assert strings["clip.std-gradient.field.direction.option.to_top_right"] == "To Top Right"
