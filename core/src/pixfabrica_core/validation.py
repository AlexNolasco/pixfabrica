"""Shared validation helpers for clip/job deserialization."""

from __future__ import annotations

from typing import Any


def snap_float(value: float, step: float) -> float:
    """Snap *value* to the nearest *step* increment."""
    if step <= 0:
        return value
    return round(value / step) * step


def _field_multiple_of(field_info: Any) -> float | None:
    for meta in field_info.metadata:
        if (step := getattr(meta, "multiple_of", None)) is not None:
            return float(step)
    return None


def _field_bounds(field_info: Any) -> tuple[float | None, float | None]:
    lo: float | None = None
    hi: float | None = None
    for meta in field_info.metadata:
        if (ge := getattr(meta, "ge", None)) is not None:
            lo = float(ge)
        if (le := getattr(meta, "le", None)) is not None:
            hi = float(le)
    return lo, hi


def snap_payload_fields(cls: type[Any], data: dict[str, Any]) -> dict[str, Any]:
    """Snap float fields in *data* to their schema ``multiple_of`` step and
    clamp them into their ``ge``/``le`` bounds.

    Pydantic's ``multiple_of`` check is strict about binary floats (e.g. ``0.25``
    fails ``multiple_of=0.1``). Workers re-validate ``model_dump(mode="json")``
    payloads, so we normalize stepped floats before ``model_validate``.

    Clamping keeps documents loadable after a plugin narrows a field's range:
    a stale stored value snaps to the nearest valid bound instead of failing
    the whole deserialization.
    """
    if not isinstance(data, dict):
        return data

    fields = getattr(cls, "model_fields", None)
    if not fields:
        return data

    out = dict(data)
    for name, field_info in fields.items():
        if name not in out:
            continue
        raw = out[name]
        if not isinstance(raw, (int, float)) or isinstance(raw, bool):
            continue
        value = float(raw)
        step = _field_multiple_of(field_info)
        if step is not None:
            value = snap_float(value, step)
        lo, hi = _field_bounds(field_info)
        if lo is not None and value < lo:
            value = lo
        if hi is not None and value > hi:
            value = hi
        if value != float(raw) or step is not None:
            out[name] = value
    return out
