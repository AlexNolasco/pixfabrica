"""Registry for per-clip effect plugins."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pixfabrica_core.validation import snap_payload_fields

if TYPE_CHECKING:
    from pixfabrica_core.composition.effect_def import EffectInstance

_EFFECT_REGISTRY: dict[str, type[EffectInstance]] = {}


def register_effect(cls: type[EffectInstance]) -> None:
    if cls.effect_type:
        _EFFECT_REGISTRY[cls.effect_type] = cls


def get_effect_class(effect_type: str) -> type[EffectInstance] | None:
    return _EFFECT_REGISTRY.get(effect_type)


def deserialize_effect(data: dict[str, Any]) -> EffectInstance:
    from pixfabrica_core.composition.unknown import UnknownEffect

    effect_type = data.get("effect_type", "")
    cls = _EFFECT_REGISTRY.get(effect_type)
    if cls is None:
        return UnknownEffect(
            id=data.get("id", ""),
            raw_effect_type=effect_type,
            raw_data=data,
        )
    return cls.model_validate(snap_payload_fields(cls, data))


def deserialize_effects(raw: Any) -> list[EffectInstance]:
    if not isinstance(raw, list):
        return []
    out: list[EffectInstance] = []
    for item in raw:
        if isinstance(item, dict):
            out.append(deserialize_effect(item))
        elif isinstance(item, EffectInstance):
            out.append(item)
    return out
