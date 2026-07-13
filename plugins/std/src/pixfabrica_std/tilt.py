"""Shared ``angle`` parameter contract for std visual plugins.

Every clip exposes a single numeric field named ``angle`` (degrees, default ``0``).
The web UI always uses the rotation slider (spinning preview, ``°`` readout,
presets ``[-45, -15, -5, 0, 5, 15, 45]``) regardless of how the renderer applies the value.

Numeric contract (all clips with ``angle``)
----------------------------
- **Units:** degrees (not radians, not unitless).
- **Sign:** positive = clockwise (matches Skia ``canvas.rotate`` and CSS ``rotate()``).
- **Negative:** counter-clockwise.

Implementation families
-----------------------
Two render paths share the same numbers; only the math differs.

**Pivot rotation** — use ``ANGLE_FULL_DESC`` and usually ``ANGLE_FULL_MIN`` / ``ANGLE_FULL_MAX``:
  ``canvas.rotate(angle)`` or GL shaders with ``radians(u_angle)`` around an anchor.
  Examples: static text, marquee, background image, vinyl record, glow text, svg icon.

**Band tilt (skew)** — use ``ANGLE_BAND_DESC`` and ``ANGLE_BAND_SKEW_MIN`` / ``ANGLE_BAND_SKEW_MAX``:
  Horizontal strips stay vertical on the left; the right edge shifts by
  ``band_skew_px(width, angle) == tan(angle) * width``.
  Examples: progress bar, sweep lines, gradient fill, solid background, waveform band.
  Skew limits stop at ``±89`` because ``tan(±90°)`` is undefined.
  Some GL band shaders negate in the fragment stage; clip ``prepare()`` may flip sign
  so the shared contract still reads as clockwise to the user.

Choosing a range
----------------
- ``±90`` — enough for tilted bands; keeps presets meaningful.
- ``±360`` — full layer rotation (text, images, icons).

UI copy vs schema
-----------------
- Field ``description`` uses ``ANGLE_BAND_DESC`` or ``ANGLE_FULL_DESC`` below.
- ``pixfabrica plugin gen-nls`` copies those strings into ``schema.nls.json``.
"""

from __future__ import annotations

import math

ANGLE_BAND_MIN = -90.0
ANGLE_BAND_MAX = 90.0
ANGLE_BAND_SKEW_MIN = -89.0
ANGLE_BAND_SKEW_MAX = 89.0
ANGLE_FULL_MIN = -360.0
ANGLE_FULL_MAX = 360.0

ANGLE_BAND_DESC = "Tilt in degrees; positive tilts up left→right"
ANGLE_FULL_DESC = "Rotation in degrees, clockwise"


def band_skew_px(width: float, angle_deg: float) -> float:
    """Horizontal skew for band tilt (``tan(angle) * width``).

    Skia top-down paths subtract this from right-edge Y coordinates.
    GL band shaders use the same value with ``center_y + (skew_px / width) * px``
    in bounds-local Y-up coordinates.
    """
    return math.tan(math.radians(angle_deg)) * width


def band_left_center_y(height: float, offset_y: float, skew_px: float) -> float:
    """Left-edge band center (``x=0``) so mid-frame center is ``offset_y * height``.

    Band parallelograms keep a vertical left edge; ``offset_y`` is the center at
    ``x = width / 2``, not at the left edge.
    """
    return offset_y * height + skew_px / 2.0
