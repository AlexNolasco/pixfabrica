"""Shared Skia font construction for std text clips."""

from __future__ import annotations

import skia

from pixfabrica_core.fonts.skia_resolver import make_skia_font
from pixfabrica_core.theme.typography import FontSpec


def make_typography_font(spec: FontSpec, *, subpixel: bool = True) -> skia.Font:
    return make_skia_font(spec, subpixel=subpixel)
