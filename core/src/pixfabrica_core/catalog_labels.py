"""Resolve catalog UI labels from plugin NLS (Option 2 shape for the web form)."""

from __future__ import annotations

from typing import Any

from pixfabrica_core.nls_keys import (
    NLS_KIND_CLIP,
    nls_field_description_key,
    nls_field_label_key,
    nls_field_option_key,
    nls_lookup_first,
)


def _literal_wire_slug(value: Any) -> str:
    s = str(value).strip().lower()
    return s.replace(" ", "_").replace("-", "_").replace(".", "_")


def _resolve_or_f3(nls: dict[str, dict[str, str]], lang: str, key: str) -> str:
    from pixfabrica_core.catalog import nls_lookup

    return nls_lookup(nls, lang, key) or key


def _field_label_keys(type_id: str, field: str, *, catalog_kind: str) -> list[str]:
    return [nls_field_label_key(type_id, field, catalog_kind=catalog_kind)]


def _field_description_keys(type_id: str, field: str, *, catalog_kind: str) -> list[str]:
    return [nls_field_description_key(type_id, field, catalog_kind=catalog_kind)]


def _resolve_option_label(
    nls: dict[str, dict[str, str]],
    lang: str,
    *,
    type_id: str,
    field: str,
    wire: str,
    label_key_prefix: str | None,
    catalog_kind: str,
) -> str:
    if label_key_prefix:
        if label_key_prefix.startswith("enum."):
            key = f"{label_key_prefix}.{wire}"
        else:
            key = f"{label_key_prefix}.{_literal_wire_slug(wire)}"
        return _resolve_or_f3(nls, lang, key)
    keys = [
        nls_field_option_key(type_id, field, _literal_wire_slug(wire), catalog_kind=catalog_kind),
    ]
    resolved = nls_lookup_first(nls, lang, keys)
    return resolved or keys[-1]


def build_clip_labels(
    ui: dict[str, Any],
    type_id: str,
    nls: dict[str, dict[str, str]],
    lang: str,
    *,
    catalog_kind: str = NLS_KIND_CLIP,
) -> dict[str, Any]:
    """Build Option-2 labels: ``sections`` + ``fields`` for *ui* spec."""
    sections_out: dict[str, str] = {}
    fields_out: dict[str, Any] = {}

    controls = ui.get("controls")
    if not isinstance(controls, dict):
        controls = {}

    raw_sections = ui.get("sections")
    if isinstance(raw_sections, list):
        for sec in raw_sections:
            if not isinstance(sec, dict):
                continue
            sec_id = sec.get("id")
            if not isinstance(sec_id, str) or not sec_id:
                continue
            title_key = sec.get("title_key")
            if isinstance(title_key, str) and title_key:
                sections_out[sec_id] = _resolve_or_f3(nls, lang, title_key)
            else:
                sections_out[sec_id] = sec_id

            fields = sec.get("fields")
            if not isinstance(fields, list):
                continue
            for field in fields:
                if not isinstance(field, str) or not field:
                    continue
                ctrl = controls.get(field)
                if not isinstance(ctrl, dict):
                    ctrl = {}

                label = nls_lookup_first(
                    nls, lang, _field_label_keys(type_id, field, catalog_kind=catalog_kind)
                )
                entry: dict[str, Any] = {
                    "label": label
                    or _field_label_keys(type_id, field, catalog_kind=catalog_kind)[-1],
                }
                desc = nls_lookup_first(
                    nls, lang, _field_description_keys(type_id, field, catalog_kind=catalog_kind)
                )
                if desc:
                    entry["description"] = desc

                kind = ctrl.get("kind")
                if kind in ("select", "segmented_enum"):
                    opts = ctrl.get("options")
                    if isinstance(opts, list):
                        prefix = ctrl.get("label_key_prefix")
                        prefix_s = prefix if isinstance(prefix, str) else None
                        options_out: dict[str, str] = {}
                        for wire in opts:
                            w = str(wire)
                            options_out[w] = _resolve_option_label(
                                nls,
                                lang,
                                type_id=type_id,
                                field=field,
                                wire=w,
                                label_key_prefix=prefix_s,
                                catalog_kind=catalog_kind,
                            )
                        entry["options"] = options_out

                if kind == "color_stop_list":
                    item_key = ctrl.get("item_label_key")
                    if isinstance(item_key, str):
                        entry["item"] = _resolve_or_f3(nls, lang, item_key)

                fields_out[field] = entry

    presets_out: dict[str, str] = {}
    raw_presets = ui.get("presets")
    if isinstance(raw_presets, list):
        for p in raw_presets:
            if not isinstance(p, dict):
                continue
            pid = p.get("id")
            label_key = p.get("label_key")
            if isinstance(pid, str) and isinstance(label_key, str):
                presets_out[pid] = _resolve_or_f3(nls, lang, label_key)

    return {"sections": sections_out, "fields": fields_out, "presets": presets_out}


def nls_lookup_safe(nls: dict[str, dict[str, str]], lang: str, key: str) -> str | None:
    from pixfabrica_core.catalog import nls_lookup

    return nls_lookup(nls, lang, key)
