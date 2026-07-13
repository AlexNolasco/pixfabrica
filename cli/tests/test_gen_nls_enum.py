"""Tests for NLS extraction of graph Enum / StrEnum option labels."""

from __future__ import annotations

from types import SimpleNamespace

from pixfabrica_cli.commands.gen_nls import _add_enum_strings
from pixfabrica_std.common import FitMode


def test_add_enum_strings_emits_enum_keys():
    strings: dict[str, str] = {}
    _add_enum_strings(strings, SimpleNamespace(annotation=FitMode))
    assert strings["enum.FitMode.contain"] == "Contain"
    assert strings["enum.FitMode.cover"] == "Cover"
    assert strings["enum.FitMode.fit_width"] == "Fit Width"
