"""Cross-plugin property field order contract for clip Parameters UI.

The Properties pane follows **Pydantic declaration order** on each clip class
(``gen-ui`` reads ``model_fields.keys()``). Reorder fields in the clip model —
do not use ``schema.ui.overrides.json`` ``sections`` just to reorder.

Three blocks (declare contiguously where applicable)
----------------------------------------------------
1. **Identity** — ``bus_select`` (if present, always first — ``AudioVisualMixin``
   MRO) → content (``text``, ``source``, ``title``, …) → appearance (colors, glow,
   background, transport styling, progress colors, …).

2. **Layout** — canonical geometry order (only fields the clip declares):

   ``offset_x → offset_y → padding_x → padding_y → width → height → angle → opacity``

   Slot aliases (same position, keep the field name):

   - ``band_height`` occupies the ``height`` slot.
   - ``content_inset_x`` is content-row tuning (cover/transport inset), not band layout.

3. **Tuning** — clip-specific params (``cover_scale``, ``transport_scale``,
   ``text_gap``, ``fit``, …).

Effect clips without layout fields: ``bus_select`` → primary effect params → tuning.

Out of scope: theme/config/job settings (no layout block).

Std plugins may also document clip-specific numeric contracts (e.g. ``angle`` in
``pixfabrica_std.tilt``); this module covers **UI field order only**.
"""

from __future__ import annotations

# Canonical layout block order (reference for authors and future lint; not runtime sorting).
LAYOUT_FIELD_ORDER: tuple[str, ...] = (
    "offset_x",
    "offset_y",
    "padding_x",
    "padding_y",
    "width",
    "height",
    "angle",
    "opacity",
)

# Fields that occupy a canonical slot under an alternate name.
LAYOUT_FIELD_SLOTS: dict[str, str] = {
    "band_height": "height",
}
