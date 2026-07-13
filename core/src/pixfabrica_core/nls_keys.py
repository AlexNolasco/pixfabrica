"""NLS key conventions for clips, effects, and project settings."""

from __future__ import annotations

NLS_KIND_CLIP = "clip"
NLS_KIND_EFFECT = "effect"
NLS_KIND_SETTING = "setting"

ALL_CATALOG_KINDS: tuple[str, ...] = (NLS_KIND_CLIP, NLS_KIND_EFFECT, NLS_KIND_SETTING)

# Known project-setting type IDs (NLS prefix ``setting.*``).
KNOWN_SETTING_TYPE_IDS: frozenset[str] = frozenset(
    {
        "std-basic-themes",
        "std-default-typography",
    }
)


def nls_type_prefix(catalog_kind: str, type_id: str) -> str:
    """``clip.std-cloud``, ``effect.std-blur-skia``, or ``setting.std-basic-themes``."""
    return f"{catalog_kind}.{type_id}"


def nls_label_key(type_id: str, *, catalog_kind: str = NLS_KIND_CLIP) -> str:
    return f"{catalog_kind}.{type_id}.label"


def nls_description_key(type_id: str, *, catalog_kind: str = NLS_KIND_CLIP) -> str:
    return f"{catalog_kind}.{type_id}.description"


def nls_field_label_key(type_id: str, field: str, *, catalog_kind: str = NLS_KIND_CLIP) -> str:
    return f"{catalog_kind}.{type_id}.field.{field}.label"


def nls_field_description_key(
    type_id: str, field: str, *, catalog_kind: str = NLS_KIND_CLIP
) -> str:
    return f"{catalog_kind}.{type_id}.field.{field}.description"


def nls_field_option_key(
    type_id: str, field: str, wire_slug: str, *, catalog_kind: str = NLS_KIND_CLIP
) -> str:
    return f"{catalog_kind}.{type_id}.field.{field}.option.{wire_slug}"


def nls_ui_section_key(type_id: str, section_id: str, *, catalog_kind: str = NLS_KIND_CLIP) -> str:
    return f"ui.{catalog_kind}.{type_id}.section.{section_id}"


def nls_lookup_first(
    nls: dict[str, dict[str, str]],
    lang: str,
    keys: list[str],
) -> str:
    from pixfabrica_core.catalog import nls_lookup

    for key in keys:
        value = nls_lookup(nls, lang, key)
        if value:
            return value
    return ""


def nls_lookup_type(
    nls: dict[str, dict[str, str]],
    lang: str,
    type_id: str,
    suffix: str,
    *,
    catalog_kinds: tuple[str, ...] = ALL_CATALOG_KINDS,
) -> str:
    """Resolve ``{kind}.{type_id}.{suffix}`` trying kinds in order."""
    keys = [f"{kind}.{type_id}.{suffix}" for kind in catalog_kinds]
    return nls_lookup_first(nls, lang, keys)
