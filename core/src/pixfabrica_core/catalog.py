from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pixfabrica_core.clips import ClipCategory, ClipGL, ClipSkia, GLPostProcessClip, VisualClip
from pixfabrica_core.composition.effect_def import EffectBackend
from pixfabrica_core.composition.icon_registry import ClipIconContext, resolve_icon
from pixfabrica_core.file_upload_policy import FileUploadPolicy, build_file_upload_policy_index
from pixfabrica_core.license_policy import resolve_clip_license, resolve_plugin_license

if TYPE_CHECKING:
    from pixfabrica_core.plugins.discovery import DiscoveredPlugin

TrackKind = Literal["skia", "gl", "post"]


@dataclass(frozen=True, slots=True)
class ClipCatalogEntry:
    clip_type: str
    category: str
    tags: list[str]
    description: str
    icon: str
    parameters: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ClipCatalogListItem:
    """Picker-facing catalog row (no JSON Schema — detail endpoint later)."""

    clip_type: str
    label: str
    description: str
    icon: str
    track_kind: TrackKind
    category: str
    tags: list[str]
    plugin_id: str
    disabled: bool
    pinned: bool
    license: str
    restricted_reason: str | None = None


@dataclass(frozen=True, slots=True)
class CachedCatalogClip:
    clip_type: str
    track_kind: TrackKind
    category: str
    tags: tuple[str, ...]
    icon: str
    plugin_id: str
    plugin_disabled: bool
    plugin_pinned: bool
    license: str
    description_fallback: str
    nls: dict[str, dict[str, str]]


@dataclass(frozen=True, slots=True)
class ClipCatalogDetail:
    clip_type: str
    plugin_id: str
    ui: dict[str, Any]
    defaults: dict[str, Any]
    parameters_schema: dict[str, Any]
    labels: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class CachedCatalogEffect:
    effect_type: str
    effect_backend: EffectBackend
    category: str
    tags: tuple[str, ...]
    icon: str
    plugin_id: str
    plugin_disabled: bool
    plugin_pinned: bool
    license: str
    description_fallback: str
    nls: dict[str, dict[str, str]]


@dataclass(frozen=True, slots=True)
class EffectCatalogListItem:
    effect_type: str
    label: str
    description: str
    icon: str
    effect_backend: EffectBackend
    category: str
    tags: list[str]
    plugin_id: str
    disabled: bool
    pinned: bool
    license: str
    restricted_reason: str | None = None


@dataclass(frozen=True, slots=True)
class CatalogCache:
    clips: tuple[CachedCatalogClip, ...]
    details: dict[str, ClipCatalogDetail]
    effects: tuple[CachedCatalogEffect, ...] = ()
    effect_details: dict[str, ClipCatalogDetail] = field(default_factory=dict)
    file_upload_policies: dict[tuple[str, str], FileUploadPolicy] = field(default_factory=dict)


def infer_track_kind(clip_cls: type) -> TrackKind | None:
    """Derive timeline track compatibility from the clip class base type (no plugin metadata)."""

    try:
        if not issubclass(clip_cls, VisualClip):
            return None
    except TypeError:
        return None
    if issubclass(clip_cls, GLPostProcessClip):
        return "post"
    if issubclass(clip_cls, ClipSkia):
        return "skia"
    if issubclass(clip_cls, ClipGL):
        return "gl"
    return None


def load_plugin_nls(plugin_package_dir: Path) -> dict[str, dict[str, str]]:
    path = plugin_package_dir / "schema.nls.json"
    if not path.is_file():
        return {"en": {}}
    with contextlib.suppress(json.JSONDecodeError, OSError):
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return {
                loc: table
                for loc, table in raw.items()
                if isinstance(loc, str) and isinstance(table, dict)
            }
    return {"en": {}}


def nls_lookup(nls: dict[str, dict[str, str]], lang: str, key: str) -> str | None:
    for locale in (lang, "en"):
        table = nls.get(locale)
        if isinstance(table, dict) and key in table:
            value = table[key]
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def humanize_clip_type(clip_type: str) -> str:
    name = clip_type.removeprefix("std-")
    return " ".join(part.capitalize() for part in name.replace("-", "_").split("_") if part)


def resolve_type_label(
    nls: dict[str, dict[str, str]],
    lang: str,
    type_id: str,
    *,
    catalog_kinds: tuple[str, ...],
) -> str:
    from pixfabrica_core.nls_keys import nls_lookup_type

    label = nls_lookup_type(nls, lang, type_id, "label", catalog_kinds=catalog_kinds)
    return label or humanize_clip_type(type_id)


def resolve_type_description(
    nls: dict[str, dict[str, str]],
    lang: str,
    type_id: str,
    fallback: str,
    *,
    catalog_kinds: tuple[str, ...],
) -> str:
    from pixfabrica_core.nls_keys import nls_lookup_type

    return (
        nls_lookup_type(nls, lang, type_id, "description", catalog_kinds=catalog_kinds) or fallback
    )


def resolve_clip_label(nls: dict[str, dict[str, str]], lang: str, clip_type: str) -> str:
    from pixfabrica_core.nls_keys import NLS_KIND_CLIP

    return resolve_type_label(nls, lang, clip_type, catalog_kinds=(NLS_KIND_CLIP,))


def resolve_effect_label(nls: dict[str, dict[str, str]], lang: str, effect_type: str) -> str:
    from pixfabrica_core.nls_keys import NLS_KIND_EFFECT

    return resolve_type_label(nls, lang, effect_type, catalog_kinds=(NLS_KIND_EFFECT,))


def resolve_clip_description(
    nls: dict[str, dict[str, str]], lang: str, clip_type: str, fallback: str
) -> str:
    from pixfabrica_core.nls_keys import NLS_KIND_CLIP

    return resolve_type_description(nls, lang, clip_type, fallback, catalog_kinds=(NLS_KIND_CLIP,))


def resolve_effect_description(
    nls: dict[str, dict[str, str]], lang: str, effect_type: str, fallback: str
) -> str:
    from pixfabrica_core.nls_keys import NLS_KIND_EFFECT

    return resolve_type_description(
        nls, lang, effect_type, fallback, catalog_kinds=(NLS_KIND_EFFECT,)
    )


def infer_effect_backend(effect_cls: type) -> EffectBackend | None:
    from pixfabrica_core.composition.effect_def import EffectInstance

    try:
        if not issubclass(effect_cls, EffectInstance):
            return None
    except TypeError:
        return None
    return effect_cls.effect_backend


def catalog_entry_for_clip_class(clip_cls: type) -> ClipCatalogEntry | None:
    clip_type = getattr(clip_cls, "clip_type", None)
    if not clip_type:
        return None

    category = str(getattr(clip_cls, "clip_category", ClipCategory.UTILITY))
    tags = [str(t) for t in getattr(clip_cls, "clip_tags", [])]
    ctx = ClipIconContext(clip_type=clip_type, category=category, tags=tags)
    icon = resolve_icon(ctx)
    if not icon:
        from pixfabrica_core.composition.icons import FALLBACK_ICON

        icon = FALLBACK_ICON

    parameters: dict[str, Any] = {}
    with contextlib.suppress(Exception):
        parameters = clip_cls.model_json_schema()

    return ClipCatalogEntry(
        clip_type=clip_type,
        category=category,
        tags=tags,
        description=(clip_cls.__doc__ or "").strip(),
        icon=icon,
        parameters=parameters,
    )


def build_clip_catalog(plugins: list[DiscoveredPlugin]) -> list[ClipCatalogEntry]:
    entries: list[ClipCatalogEntry] = []
    for plugin in plugins:
        for clip_cls in plugin.clip_types:
            entry = catalog_entry_for_clip_class(clip_cls)
            if entry is not None:
                entries.append(entry)
    return entries


def build_catalog_cache(
    plugins: list[DiscoveredPlugin],
    *,
    disabled_plugin_ids: set[str] | None = None,
    pinned_plugin_ids: set[str] | None = None,
) -> CatalogCache:
    from pixfabrica_core.catalog_ui import (
        extract_defaults_from_clip_class,
        load_plugin_ui_files,
        merged_ui_spec_for_clip,
        parameters_schema_for_clip_class,
    )

    disabled = disabled_plugin_ids or set()
    pinned = pinned_plugin_ids or set()
    cached: list[CachedCatalogClip] = []
    details: dict[str, ClipCatalogDetail] = {}
    cached_effects: list[CachedCatalogEffect] = []
    effect_details: dict[str, ClipCatalogDetail] = {}

    for plugin in plugins:
        nls = load_plugin_nls(plugin.plugin_package_dir)
        ui_generated, ui_overrides = load_plugin_ui_files(plugin.plugin_package_dir)
        plugin_disabled = plugin.package_name in disabled
        plugin_pinned = plugin.package_name in pinned
        plugin_license = resolve_plugin_license(plugin.manifest)

        for clip_cls in plugin.clip_types:
            track_kind = infer_track_kind(clip_cls)
            if track_kind is None:
                continue

            clip_type = getattr(clip_cls, "clip_type", None)
            if not clip_type:
                continue

            category = str(getattr(clip_cls, "clip_category", ClipCategory.UTILITY))
            tags = tuple(str(t) for t in getattr(clip_cls, "clip_tags", []))
            ctx = ClipIconContext(clip_type=clip_type, category=category, tags=list(tags))
            icon = resolve_icon(ctx)
            if not icon:
                from pixfabrica_core.composition.icons import FALLBACK_ICON

                icon = FALLBACK_ICON

            doc = (clip_cls.__doc__ or "").strip()
            first_para = doc.split("\n\n")[0] if doc else ""
            description_fallback = " ".join(first_para.split())

            cached.append(
                CachedCatalogClip(
                    clip_type=clip_type,
                    track_kind=track_kind,
                    category=category,
                    tags=tags,
                    icon=icon,
                    plugin_id=plugin.package_name,
                    plugin_disabled=plugin_disabled,
                    plugin_pinned=plugin_pinned,
                    license=resolve_clip_license(clip_cls, plugin_license),
                    description_fallback=description_fallback,
                    nls=nls,
                )
            )

            parameters_schema = parameters_schema_for_clip_class(clip_cls)

            ui_spec = merged_ui_spec_for_clip(ui_generated, ui_overrides, clip_type)
            if ui_spec is not None:
                defaults = extract_defaults_from_clip_class(clip_cls)
                details[clip_type] = ClipCatalogDetail(
                    clip_type=clip_type,
                    plugin_id=plugin.package_name,
                    ui=ui_spec,
                    defaults=defaults,
                    parameters_schema=parameters_schema,
                )

        for effect_cls in plugin.effects:
            backend = infer_effect_backend(effect_cls)
            if backend is None:
                continue
            effect_type = getattr(effect_cls, "effect_type", None)
            if not effect_type:
                continue
            category = str(getattr(effect_cls, "clip_category", ClipCategory.EFFECTS))
            tags = tuple(str(t) for t in getattr(effect_cls, "clip_tags", []))
            ctx = ClipIconContext(clip_type=effect_type, category=category, tags=list(tags))
            icon = resolve_icon(ctx)
            if not icon:
                from pixfabrica_core.composition.icons import FALLBACK_ICON

                icon = FALLBACK_ICON
            doc = (effect_cls.__doc__ or "").strip()
            first_para = doc.split("\n\n")[0] if doc else ""
            description_fallback = " ".join(first_para.split())
            cached_effects.append(
                CachedCatalogEffect(
                    effect_type=effect_type,
                    effect_backend=backend,
                    category=category,
                    tags=tags,
                    icon=icon,
                    plugin_id=plugin.package_name,
                    plugin_disabled=plugin_disabled,
                    plugin_pinned=plugin_pinned,
                    license=resolve_clip_license(effect_cls, plugin_license),
                    description_fallback=description_fallback,
                    nls=nls,
                )
            )
            parameters_schema = parameters_schema_for_clip_class(effect_cls)
            ui_spec = merged_ui_spec_for_clip(ui_generated, ui_overrides, effect_type)
            if ui_spec is not None:
                defaults = extract_defaults_from_clip_class(effect_cls)
                effect_details[effect_type] = ClipCatalogDetail(
                    clip_type=effect_type,
                    plugin_id=plugin.package_name,
                    ui=ui_spec,
                    defaults=defaults,
                    parameters_schema=parameters_schema,
                )

    return CatalogCache(
        clips=tuple(cached),
        details=details,
        effects=tuple(cached_effects),
        effect_details=effect_details,
        file_upload_policies=build_file_upload_policy_index(plugins),
    )


def get_catalog_detail(
    cache: CatalogCache, clip_type: str, *, lang: str = "en"
) -> ClipCatalogDetail | None:
    detail = cache.details.get(clip_type)
    if detail is None:
        return None
    cached = next((n for n in cache.clips if n.clip_type == clip_type), None)
    if cached is None:
        return detail
    from pixfabrica_core.catalog_labels import build_clip_labels

    labels = build_clip_labels(detail.ui, clip_type, cached.nls, lang)
    return ClipCatalogDetail(
        clip_type=detail.clip_type,
        plugin_id=cached.plugin_id,
        ui=detail.ui,
        defaults=detail.defaults,
        parameters_schema=detail.parameters_schema,
        labels=labels,
    )


def validate_upload_clip_context(cache: CatalogCache, clip_type: str, plugin_id: str) -> bool:
    """Return True when clip_type is owned by plugin_id in the catalog."""
    return any(n.clip_type == clip_type and n.plugin_id == plugin_id for n in cache.clips)


def resolve_file_upload_policy(
    cache: CatalogCache,
    *,
    clip_type: str,
    plugin_id: str,
    field: str,
) -> FileUploadPolicy | None:
    """Return the upload policy for a catalog clip file field, if declared and owned."""
    if not validate_upload_clip_context(cache, clip_type, plugin_id):
        return None
    return cache.file_upload_policies.get((clip_type, field))


def get_effect_catalog_detail(
    cache: CatalogCache, effect_type: str, *, lang: str = "en"
) -> ClipCatalogDetail | None:
    effect_details = cache.effect_details or {}
    detail = effect_details.get(effect_type)
    if detail is None:
        return None
    effect = next((e for e in cache.effects if e.effect_type == effect_type), None)
    if effect is None:
        return detail
    from pixfabrica_core.catalog_labels import build_clip_labels
    from pixfabrica_core.nls_keys import NLS_KIND_EFFECT

    labels = build_clip_labels(
        detail.ui, effect_type, effect.nls, lang, catalog_kind=NLS_KIND_EFFECT
    )
    return ClipCatalogDetail(
        clip_type=detail.clip_type,
        plugin_id=detail.plugin_id,
        ui=detail.ui,
        defaults=detail.defaults,
        parameters_schema=detail.parameters_schema,
        labels=labels,
    )


def list_effect_catalog_items(
    cache: CatalogCache,
    *,
    lang: str = "en",
    effect_backend: EffectBackend | None = None,
) -> list[EffectCatalogListItem]:
    items: list[EffectCatalogListItem] = []
    for effect in cache.effects:
        if effect_backend is not None and effect.effect_backend != effect_backend:
            continue
        items.append(
            EffectCatalogListItem(
                effect_type=effect.effect_type,
                label=resolve_effect_label(effect.nls, lang, effect.effect_type),
                description=resolve_effect_description(
                    effect.nls, lang, effect.effect_type, effect.description_fallback
                ),
                icon=effect.icon,
                effect_backend=effect.effect_backend,
                category=effect.category,
                tags=list(effect.tags),
                plugin_id=effect.plugin_id,
                disabled=effect.plugin_disabled,
                pinned=effect.plugin_pinned,
                license=effect.license,
            )
        )
    return items


def list_catalog_items(
    cache: CatalogCache,
    *,
    lang: str = "en",
    track_kind: TrackKind | None = None,
) -> list[ClipCatalogListItem]:
    items: list[ClipCatalogListItem] = []
    for clip in cache.clips:
        if track_kind is not None and clip.track_kind != track_kind:
            continue
        items.append(
            ClipCatalogListItem(
                clip_type=clip.clip_type,
                label=resolve_clip_label(clip.nls, lang, clip.clip_type),
                description=resolve_clip_description(
                    clip.nls, lang, clip.clip_type, clip.description_fallback
                ),
                icon=clip.icon,
                track_kind=clip.track_kind,
                category=clip.category,
                tags=list(clip.tags),
                plugin_id=clip.plugin_id,
                disabled=clip.plugin_disabled,
                pinned=clip.plugin_pinned,
                license=clip.license,
            )
        )
    return items
