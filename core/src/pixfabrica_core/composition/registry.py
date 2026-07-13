"""Unified clip-type registry.

Maps clip_type strings to their classes. Populated during plugin discovery —
not at import time — so the registry is always an explicit snapshot of what
plugins are loaded in the current process.

Visual clip types (Clip subclasses) and project settings (ProjectSetting
subclasses) live in separate registries since they have different contracts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pixfabrica_core.validation import snap_payload_fields

if TYPE_CHECKING:
    from pixfabrica_core.clips.base import Clip
    from pixfabrica_core.composition.config import ProjectSetting

_CLIP_TYPE_REGISTRY: dict[str, type[Clip]] = {}
_SETTING_REGISTRY: dict[str, type[ProjectSetting]] = {}


def register_clip_type(cls: type[Clip]) -> None:
    """Register a visual clip-type class by its clip_type."""
    if cls.clip_type:
        _CLIP_TYPE_REGISTRY[cls.clip_type] = cls


def register_setting_type(cls: type[ProjectSetting]) -> None:
    """Register a project setting class by its setting_type."""
    if cls.setting_type:
        _SETTING_REGISTRY[cls.setting_type] = cls


def deserialize_clip(data: dict[str, Any]) -> Clip:
    """Deserialize a track clip, including nested ``effects`` when present."""
    from pixfabrica_core.clips.visual import VisualClip
    from pixfabrica_core.composition.effect_registry import deserialize_effects

    raw_effects = data.get("effects")
    payload = {k: v for k, v in data.items() if k != "effects"}
    clip = _deserialize_clip_payload(payload)
    if isinstance(clip, VisualClip) and raw_effects is not None:
        clip = clip.model_copy(update={"effects": deserialize_effects(raw_effects)})
    return clip


def _deserialize_clip_payload(data: dict[str, Any]) -> Clip:
    """Deserialize a visual clip dict without resolving nested effects."""
    from pixfabrica_core.composition.unknown import UnknownClip

    clip_type = data.get("clip_type", "")
    cls = _CLIP_TYPE_REGISTRY.get(clip_type)
    if cls is None:
        return UnknownClip(
            id=data.get("id", ""),
            raw_clip_type=clip_type,
            raw_data=data,
        )
    return cls.model_validate(snap_payload_fields(cls, data))


def deserialize_setting(data: dict[str, Any]) -> ProjectSetting:
    """Deserialize a project setting, returning UnknownProjectSetting for unknown types."""
    from pixfabrica_core.composition.unknown import UnknownProjectSetting

    setting_type = data.get("setting_type", "")
    cls = _SETTING_REGISTRY.get(setting_type)
    if cls is None:
        return UnknownProjectSetting(
            id=data.get("id", ""),
            raw_setting_type=setting_type,
            raw_data=data,
        )
    return cls.model_validate(snap_payload_fields(cls, data))
