"""Generate schema.ui.generated.json (+ bootstrap overrides) for a plugin."""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from types import UnionType
from typing import Annotated, Any, get_args, get_origin

import typer
from pydantic import BaseModel
from pydantic.fields import FieldInfo
from rich.console import Console
from rich.table import Table

from pixfabrica_cli.commands.gen_nls import _load_plugin
from pixfabrica_cli.graph_enum_schema import (
    enum_class_from_annotation,
    enum_wire_option_strings,
)
from pixfabrica_cli.literal_schema import (
    literal_label_key_prefix,
    literal_tuple_from_annotation,
)
from pixfabrica_core.media_upload import (
    accept_for_kind,
    kind_for_clip_category,
    max_bytes_for_kind,
)
from pixfabrica_core.nls_keys import (
    NLS_KIND_CLIP,
    NLS_KIND_EFFECT,
    NLS_KIND_SETTING,
    nls_ui_section_key,
)
from pixfabrica_core.plugins import plugin_clip_types
from pixfabrica_core.theme.typography import FontRole
from pixfabrica_core.ui_schema import (
    field_section_id,
    field_stock_browse,
    field_stock_media_kind,
    field_stock_role,
    field_stock_source_field,
)

console = Console()

_TIMING_FIELDS: frozenset[str] = frozenset({"start", "duration", "enabled"})
# System-assigned clip id — keep in ``controls`` for merge/parity but omit from sections.
_FIELDS_HIDDEN_FROM_SECTIONS: frozenset[str] = frozenset({"id", "effects"})
_SCHEMA_VERSION = 1

_FONT_ROLES: frozenset[str] = frozenset(str(r) for r in get_args(FontRole))


_ANGLE_DEFAULT_PRESETS: list[int] = [-90, -45, -15, -5, 0, 5, 15, 45, 90]


def _uses_rotation_slider(name: str, ge: float | None, le: float | None) -> bool:
    if ge is None or le is None:
        return False
    if name == "angle":
        return True
    if name == "rotation":
        return ge == 0.0 and le == 360.0
    return False


def _rotation_slider_control(
    *, ge: float = 0.0, le: float = 360.0, optional: bool = False
) -> dict[str, Any]:
    presets = [p for p in _ANGLE_DEFAULT_PRESETS if ge <= p <= le]
    out: dict[str, Any] = {
        "kind": "slider",
        "show_as": "rotation",
        "minimum": ge,
        "maximum": le,
        "presets": presets,
        "step": 1.0,
    }
    if optional:
        out["nullable"] = True
    return out


def _anchor_axis_for_field(name: str) -> str | None:
    if name == "offset_x":
        return "x"
    if name == "offset_y":
        return "y"
    return None


def _unit_interval_slider_control(name: str, *, optional: bool = False) -> dict[str, Any]:
    axis = _anchor_axis_for_field(name)
    if axis is not None:
        return {"kind": "slider", "show_as": "anchor", "axis": axis}
    show = "fraction" if optional else "percent"
    out: dict[str, Any] = {"kind": "slider", "show_as": show}
    if optional:
        out["nullable"] = True
    return out


def _is_upload_source_field(name: str) -> bool:
    if name in ("source_provider", "source_attribution"):
        return False
    return name == "source" or name.endswith("_source")


def _file_control(clip_category: object, *, optional: bool = False) -> dict[str, Any]:
    upload_kind = kind_for_clip_category(clip_category)
    out: dict[str, Any] = {
        "kind": "file",
        "upload_kind": upload_kind,
        "accept": accept_for_kind(upload_kind),
        "max_bytes": max_bytes_for_kind(upload_kind),
    }
    if optional:
        out["nullable"] = True
    return out


def _prop_is_nullable(prop: dict[str, Any]) -> bool:
    t = prop.get("type")
    if isinstance(t, list):
        return "null" in t
    return False


def _json_schema_type(prop: dict[str, Any]) -> str | list[str] | None:
    t = prop.get("type")
    if isinstance(t, list):
        non_null = [x for x in t if x != "null"]
        return non_null[0] if len(non_null) == 1 else t
    return t


def _infer_from_json_schema_property(
    name: str, prop: dict[str, Any], clip_category: object | None = None
) -> dict[str, Any]:
    """Map a single JSON Schema property to a control dict (best-effort)."""
    if prop.get("anyOf") or prop.get("oneOf") or prop.get("allOf"):
        return {"kind": "unknown", "reason": "composite_schema", "detail": name}

    if "enum" in prop:
        vals = prop["enum"]
        opts = [str(v) for v in vals]
        if len(opts) <= 5 and all(isinstance(v, str) for v in vals):
            return {"kind": "segmented_enum", "options": opts}
        return {"kind": "select", "options": opts}

    jt = _json_schema_type(prop)
    if jt == "boolean":
        return {"kind": "toggle"}
    if jt == "string":
        if name == "text":
            return {"kind": "textarea", "rows": 4}
        if _is_upload_source_field(name) and clip_category is not None:
            return _file_control(clip_category, optional=_prop_is_nullable(prop))
        return {"kind": "text"}
    if jt in ("number", "integer"):
        mn = (
            prop.get("minimum") if prop.get("minimum") is not None else prop.get("exclusiveMinimum")
        )
        mx = (
            prop.get("maximum") if prop.get("maximum") is not None else prop.get("exclusiveMaximum")
        )
        if mn is not None and mx is not None:
            if _uses_rotation_slider(name, float(mn), float(mx)):
                return _rotation_slider_control(ge=float(mn), le=float(mx))
            if mn == 0.0 and mx == 1.0:
                return _unit_interval_slider_control(name)
            return {"kind": "slider", "minimum": mn, "maximum": mx}
        if mn is not None:
            return {"kind": "slider", "minimum": mn}
        return {"kind": "number"}

    return {
        "kind": "unknown",
        "reason": "unhandled_json_schema_type",
        "detail": name,
        "json_type": jt,
    }


def _ge_le_from_metadata(metadata: list[Any]) -> tuple[float | None, float | None]:
    ge: float | None = None
    le: float | None = None
    for m in metadata:
        cn = m.__class__.__name__
        if cn == "Ge":
            ge = m.ge
        elif cn == "Gt":
            ge = m.gt
        elif cn == "Le":
            le = m.le
        elif cn == "Lt":
            le = m.lt
    return ge, le


def _multiple_of_from_metadata(metadata: list[Any]) -> float | None:
    for m in metadata:
        if m.__class__.__name__ == "MultipleOf":
            return float(m.multiple_of)
    return None


def _prop_schema_for_field(
    finfo: FieldInfo, prop_schema: dict[str, Any] | None
) -> dict[str, Any] | None:
    """Merge JSON Schema property with Field() metadata (needed when model_json_schema fails)."""
    out: dict[str, Any] = dict(prop_schema) if isinstance(prop_schema, dict) else {}
    meta = list(finfo.metadata)
    ge, le = _ge_le_from_metadata(meta)
    if ge is not None:
        out.setdefault("minimum", ge)
    if le is not None:
        out.setdefault("maximum", le)
    mo = _multiple_of_from_metadata(meta)
    if mo is not None:
        out["multipleOf"] = mo
    if finfo.annotation is int and "type" not in out:
        out["type"] = "integer"
    return out or None


def _min_len_from_metadata(metadata: list[Any]) -> int | None:
    for m in metadata:
        if m.__class__.__name__ == "MinLen" and hasattr(m, "min_length"):
            return int(m.min_length)
    return None


def _max_len_from_metadata(metadata: list[Any]) -> int | None:
    for m in metadata:
        if m.__class__.__name__ == "MaxLen" and hasattr(m, "max_length"):
            return int(m.max_length)
    return None


def _list_item_base_model(annotation: Any) -> type[BaseModel] | None:
    """If *annotation* is ``list[T]`` with ``T`` a ``BaseModel``, return ``T``."""
    origin = get_origin(annotation)
    if origin is not list:
        return None
    args = get_args(annotation)
    if len(args) != 1:
        return None
    item = args[0]
    if isinstance(item, type) and issubclass(item, BaseModel):
        return item
    return None


def _is_color_stop_item_model(model_cls: type[BaseModel]) -> bool:
    return set(model_cls.model_fields) == {"color", "position"}


def _is_color_swatch_item_model(model_cls: type[BaseModel]) -> bool:
    return set(model_cls.model_fields) == {"color"}


def _infer_color_list_field(name: str, finfo: FieldInfo) -> dict[str, Any] | None:
    """Structured editor for single-color row models (``{color}`` only)."""
    inner = _list_item_base_model(finfo.annotation)
    if inner is None or not _is_color_swatch_item_model(inner):
        return None

    color_f = inner.model_fields["color"]
    color_ctrl = _infer_from_model_field("color", color_f, None)
    if color_ctrl.get("kind") == "unknown":
        color_ctrl = {"kind": "theme_or_color", "nullable": False}

    min_items = _min_len_from_metadata(list(finfo.metadata)) or 0
    max_items = _max_len_from_metadata(list(finfo.metadata))
    ctrl: dict[str, Any] = {
        "kind": "color_list",
        "min_items": min_items,
        "item_model": f"{inner.__module__}.{inner.__name__}",
        "item_label_key": "ui.control.color_list.item",
        "item_fields": {
            "color": color_ctrl,
        },
    }
    if max_items is not None:
        ctrl["max_items"] = max_items
    return ctrl


def _infer_color_stop_list_field(name: str, finfo: FieldInfo) -> dict[str, Any] | None:
    """Structured editor for ``ColorStop``-shaped rows (``color`` + ``position``)."""
    inner = _list_item_base_model(finfo.annotation)
    if inner is None or not _is_color_stop_item_model(inner):
        return None

    color_f = inner.model_fields["color"]
    pos_f = inner.model_fields["position"]
    color_ctrl = _infer_from_model_field("color", color_f, None)
    if color_ctrl.get("kind") == "unknown":
        color_ctrl = {"kind": "theme_or_color", "nullable": False}
    pos_ctrl = _infer_from_model_field("position", pos_f, None)

    min_items = _min_len_from_metadata(list(finfo.metadata)) or 2
    max_items = _max_len_from_metadata(list(finfo.metadata))
    ctrl: dict[str, Any] = {
        "kind": "color_stop_list",
        "min_items": min_items,
        "item_model": f"{inner.__module__}.{inner.__name__}",
        "item_label_key": "ui.control.color_stop_list.item",
        "item_fields": {
            "color": color_ctrl,
            "position": pos_ctrl,
        },
    }
    if max_items is not None:
        ctrl["max_items"] = max_items
    return ctrl


def _union_flat_members(ann: Any) -> tuple[list[Any], bool]:
    """Split Union / UnionType into non-None members; bool is True if None was a member."""
    import typing as typing_mod

    origin = get_origin(ann)
    if origin is typing_mod.Union or origin is UnionType:
        args = get_args(ann)
        optional = any(a is type(None) for a in args)
        members = [a for a in args if a is not type(None)]
        return members, optional
    return [ann], False


def _type_name(t: Any) -> str:
    return getattr(t, "__name__", str(t))


def _is_color_family_union(members: list[Any]) -> bool:
    for m in members:
        n = _type_name(m)
        if n == "ColorToken" or n == "Color":
            continue
        return False
    return bool(members)


def _maybe_typography_role_control(name: str, ctrl: dict[str, Any]) -> dict[str, Any]:
    """Use the typography role picker for ``typography_role`` / ``*_typography_role`` fields."""
    if ctrl.get("kind") not in ("select", "segmented_enum"):
        return ctrl
    if name != "typography_role" and not name.endswith("_typography_role"):
        return ctrl
    raw_opts = ctrl.get("options")
    if not isinstance(raw_opts, list) or not raw_opts:
        return ctrl
    opts = [str(o) for o in raw_opts]
    if not all(o in _FONT_ROLES for o in opts):
        return ctrl
    return {"kind": "typography_role", "options": opts}


def _enrich_enum_label_prefix(finfo: FieldInfo, ctrl: dict[str, Any]) -> dict[str, Any]:
    """Attach ``label_key_prefix`` when JSON Schema enum matches a graph ``Enum`` field."""
    if ctrl.get("label_key_prefix"):
        return ctrl
    if ctrl.get("kind") not in ("select", "segmented_enum"):
        return ctrl
    raw_opts = ctrl.get("options")
    if not isinstance(raw_opts, list) or not raw_opts:
        return ctrl
    opts_norm = [str(o) for o in raw_opts]

    ec = enum_class_from_annotation(finfo.annotation)
    if ec is None:
        return ctrl
    wire = enum_wire_option_strings(ec)
    if len(wire) != len(opts_norm) or set(wire) != set(opts_norm):
        return ctrl
    return {**ctrl, "label_key_prefix": f"enum.{ec.__name__}"}


def _enrich_literal_label_prefix(
    type_id: str | None,
    field_name: str,
    finfo: FieldInfo,
    ctrl: dict[str, Any],
    *,
    catalog_kind: str = NLS_KIND_CLIP,
) -> dict[str, Any]:
    """Attach ``label_key_prefix`` when options match a ``Literal[...]`` on the field."""
    if ctrl.get("label_key_prefix"):
        return ctrl
    if ctrl.get("kind") not in ("select", "segmented_enum"):
        return ctrl
    raw_opts = ctrl.get("options")
    if not isinstance(raw_opts, list) or not raw_opts:
        return ctrl
    lit = literal_tuple_from_annotation(finfo.annotation)
    if lit is None:
        return ctrl
    lit_norm = {str(x) for x in lit}
    if {str(o) for o in raw_opts} != lit_norm or len(raw_opts) != len(lit):
        return ctrl
    return {
        **ctrl,
        "label_key_prefix": literal_label_key_prefix(
            type_id, field_name, catalog_kind=catalog_kind
        ),
    }


def _infer_from_model_field(
    name: str,
    finfo: FieldInfo,
    type_id: str | None = None,
    clip_category: object | None = None,
    *,
    catalog_kind: str = NLS_KIND_CLIP,
) -> dict[str, Any]:
    """Infer control metadata from Pydantic FieldInfo when full JSON Schema is unavailable."""
    if name == "bus_select":
        return {"kind": "bus_select"}

    csl = _infer_color_stop_list_field(name, finfo)
    if csl is not None:
        return csl

    cl = _infer_color_list_field(name, finfo)
    if cl is not None:
        return cl

    ann = finfo.annotation
    meta = list(finfo.metadata)

    members, optional = _union_flat_members(ann)

    if len(members) >= 2:
        if _is_color_family_union(members):
            return {"kind": "theme_or_color", "nullable": optional}
        joined = " | ".join(_type_name(m) for m in members)
        return {
            "kind": "unknown",
            "reason": "union_not_classified",
            "detail": name,
            "annotation": joined,
        }

    if len(members) == 1:
        ann = members[0]

    if isinstance(ann, type) and issubclass(ann, Enum) and ann is not Enum:
        opts = enum_wire_option_strings(ann)
        if not opts:
            return {
                "kind": "unknown",
                "reason": "empty_enum",
                "detail": name,
                "annotation": ann.__name__,
            }
        prefix = f"enum.{ann.__name__}"
        if len(opts) <= 5 and issubclass(ann, str):
            return {"kind": "segmented_enum", "options": opts, "label_key_prefix": prefix}
        return {"kind": "select", "options": opts, "label_key_prefix": prefix}

    origin = get_origin(ann)
    args = get_args(ann)

    if origin is not None and getattr(origin, "__name__", "") == "Literal":
        opts = list(args)
        prefix = literal_label_key_prefix(type_id, name, catalog_kind=catalog_kind)
        if opts and all(isinstance(v, str) for v in opts) and len(opts) <= 5:
            return {"kind": "segmented_enum", "options": opts, "label_key_prefix": prefix}
        if opts:
            return {"kind": "select", "options": opts, "label_key_prefix": prefix}

    if ann is bool:
        return {"kind": "toggle"}
    if ann is str:
        if name == "text":
            return {"kind": "textarea", "rows": 4}
        if _is_upload_source_field(name) and clip_category is not None:
            return _file_control(clip_category, optional=optional)
        return {"kind": "text"}

    if ann in (int, float):
        ge, le = _ge_le_from_metadata(meta)
        if ge is not None and le is not None:
            if _uses_rotation_slider(name, ge, le):
                return _rotation_slider_control(ge=ge, le=le, optional=optional)
            if ge == 0.0 and le == 1.0:
                return _unit_interval_slider_control(name, optional=optional)
            return {"kind": "slider", "minimum": ge, "maximum": le}
        if ge is not None:
            return {"kind": "slider", "minimum": ge}
        return {"kind": "number"}

    ann_s = _type_name(ann)
    if "ColorToken" in ann_s or ann_s == "Color":
        return {"kind": "theme_or_color", "nullable": optional}

    return {
        "kind": "unknown",
        "reason": "unhandled_annotation",
        "detail": name,
        "annotation": ann_s,
    }


def _infer_step_value(ctrl: dict[str, Any], prop: dict[str, Any] | None) -> float:
    # Explicit Field(multiple_of=…) wins over show_as percent/fraction defaults (0.01).
    if prop is not None:
        mult = prop.get("multipleOf")
        if mult is not None:
            return float(mult)
    if ctrl.get("show_as") in ("percent", "fraction", "anchor"):
        return 0.01
    if prop is not None:
        jt = _json_schema_type(prop)
        if jt == "integer":
            return 1.0
    return 0.1


def _attach_step(
    name: str, ctrl: dict[str, Any], prop: dict[str, Any] | None
) -> tuple[dict[str, Any], str | None]:
    kind = ctrl.get("kind")
    if kind not in ("slider", "number"):
        return ctrl, None
    if "step" in ctrl:
        return ctrl, None
    step = _infer_step_value(ctrl, prop)
    out = {**ctrl, "step": step}
    warn: str | None = None
    if (
        out.get("minimum") is not None
        and out.get("maximum") is not None
        and step == 0.1
        and ctrl.get("show_as") not in ("percent", "fraction", "anchor")
        and not (prop and prop.get("multipleOf"))
        and not (prop and _json_schema_type(prop) == "integer")
    ):
        warn = f"{name}: minimum and maximum set but no explicit step; using default step {step}"
    return out, warn


def _apply_stock_browse(finfo: FieldInfo, ctrl: dict[str, Any]) -> dict[str, Any]:
    if ctrl.get("kind") != "file" or not field_stock_browse(finfo):
        return ctrl
    media = field_stock_media_kind(finfo)
    upload_kind = ctrl.get("upload_kind")
    if media == "image" and upload_kind == "image":
        return {**ctrl, "stock_browse": True}
    if media == "video" and upload_kind == "video":
        return {**ctrl, "stock_browse": True}
    return ctrl


def _stock_provider_control(finfo: FieldInfo) -> dict[str, Any]:
    ctrl: dict[str, Any] = {"kind": "hidden", "read_only": True}
    src = field_stock_source_field(finfo)
    if src:
        ctrl["stock_source_field"] = src
    return ctrl


def _stock_attribution_control(finfo: FieldInfo) -> dict[str, Any]:
    ctrl: dict[str, Any] = {"kind": "textarea", "rows": 3, "read_only": True}
    src = field_stock_source_field(finfo)
    if src:
        ctrl["stock_source_field"] = src
    return ctrl


def _is_stock_provider_field(name: str, finfo: FieldInfo) -> bool:
    if field_stock_role(finfo) == "provider":
        return True
    return name.endswith("_provider") and field_stock_source_field(finfo) is not None


def _is_stock_attribution_field(name: str, finfo: FieldInfo) -> bool:
    if field_stock_role(finfo) == "attribution":
        return True
    return name == "source_attribution"


def _finalize_control(
    name: str, ctrl: dict[str, Any], prop: dict[str, Any] | None
) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    kind = ctrl.get("kind")
    if kind in ("color_stop_list", "color_list"):
        item_fields = ctrl.get("item_fields")
        if isinstance(item_fields, dict):
            new_items = {}
            for sub_name, sub_ctrl in item_fields.items():
                if isinstance(sub_ctrl, dict):
                    sub_c, sub_w = _attach_step(sub_name, sub_ctrl, None)
                    warnings.extend(w for w in [sub_w] if w)
                    new_items[sub_name] = sub_c
                else:
                    new_items[sub_name] = sub_ctrl
            ctrl = {**ctrl, "item_fields": new_items}
        return ctrl, warnings
    c, w = _attach_step(name, ctrl, prop)
    if w:
        warnings.append(w)
    return c, warnings


def _properties_from_model(cls: type[BaseModel]) -> dict[str, dict[str, Any]]:
    try:
        schema = cls.model_json_schema()
        props = schema.get("properties") or {}
        if isinstance(props, dict):
            return dict(props)
    except Exception:
        pass
    return {}


def _build_controls_for_class(
    cls: type[BaseModel],
    *,
    catalog_kind: str = NLS_KIND_CLIP,
) -> tuple[dict[str, Any], list[str], list[str]]:
    """Returns (controls dict, unknown field names, step warnings)."""
    props = _properties_from_model(cls)
    controls: dict[str, Any] = {}
    unknowns: list[str] = []
    step_warnings: list[str] = []
    type_id: str | None = _plugin_type_id(cls) or None

    clip_category = getattr(cls, "clip_category", None)

    for name, finfo in cls.model_fields.items():
        if name == "id":
            controls[name] = {"kind": "hidden", "read_only": True}
            continue
        if _is_stock_provider_field(name, finfo):
            controls[name] = _stock_provider_control(finfo)
            continue
        if _is_stock_attribution_field(name, finfo):
            controls[name] = _stock_attribution_control(finfo)
            continue
        if name == "effects":
            # Per-clip effect chain — edited in Properties, not clip param UI.
            continue
        raw_prop = props.get(name) if isinstance(props.get(name), dict) else None
        prop_schema = _prop_schema_for_field(finfo, raw_prop)
        if raw_prop is not None:
            js_ctrl = _infer_from_json_schema_property(name, raw_prop, clip_category)
            if js_ctrl.get("kind") != "unknown":
                c = _enrich_enum_label_prefix(finfo, js_ctrl)
                c = _enrich_literal_label_prefix(type_id, name, finfo, c, catalog_kind=catalog_kind)
                c = _maybe_typography_role_control(name, c)
                c, warns = _finalize_control(name, c, prop_schema)
                c = _apply_stock_browse(finfo, c)
                step_warnings.extend(warns)
                controls[name] = c
                continue
        ctrl = _infer_from_model_field(
            name, finfo, type_id, clip_category, catalog_kind=catalog_kind
        )
        c = _enrich_enum_label_prefix(finfo, ctrl)
        c = _enrich_literal_label_prefix(type_id, name, finfo, c, catalog_kind=catalog_kind)
        c = _maybe_typography_role_control(name, c)
        c, warns = _finalize_control(name, c, prop_schema)
        c = _apply_stock_browse(finfo, c)
        step_warnings.extend(warns)
        controls[name] = c
        if c.get("kind") == "unknown":
            unknowns.append(name)
    return controls, unknowns, step_warnings


def _stock_attribution_coverage(cls: type[BaseModel]) -> dict[str, dict[str, bool]]:
    """Map each stock-browse source field to whether attribution/provider params exist."""
    coverage: dict[str, dict[str, bool]] = {}
    for name, finfo in cls.model_fields.items():
        if field_stock_browse(finfo):
            coverage[name] = {"attribution": False, "provider": False}

    for finfo in cls.model_fields.values():
        source = field_stock_source_field(finfo)
        role = field_stock_role(finfo)
        if source is None or role not in ("attribution", "provider"):
            continue
        if source in coverage:
            coverage[source][role] = True
    return coverage


def _validate_stock_attribution_fields(cls: type[BaseModel]) -> list[str]:
    """Warn when stock browse fields lack paired attribution/provider params."""
    warnings: list[str] = []
    for source, found in _stock_attribution_coverage(cls).items():
        missing: list[str] = []
        if not found["attribution"]:
            missing.append(f"stock_attribution_field({source!r})")
        if not found["provider"]:
            missing.append(f"stock_provider_field({source!r})")
        if missing:
            warnings.append(f"{source}: stock browse enabled but missing {' and '.join(missing)}")
    return warnings


def _section_title_key(type_id: str, section_id: str, *, catalog_kind: str = NLS_KIND_CLIP) -> str:
    if section_id == "parameters":
        return nls_ui_section_key(type_id, "parameters", catalog_kind=catalog_kind)
    return nls_ui_section_key(type_id, section_id, catalog_kind=catalog_kind)


def _build_sections(
    type_id: str,
    cls: type[BaseModel],
    *,
    catalog_kind: str = NLS_KIND_CLIP,
) -> list[dict[str, Any]]:
    field_names = list(cls.model_fields.keys())
    buckets: dict[str, list[str]] = {}
    bucket_order: list[str] = []

    for name in field_names:
        if name in _TIMING_FIELDS or name in _FIELDS_HIDDEN_FROM_SECTIONS:
            continue
        finfo = cls.model_fields[name]
        if field_stock_role(finfo) == "provider":
            continue
        section_id = field_section_id(finfo) or "parameters"
        if section_id not in buckets:
            buckets[section_id] = []
            bucket_order.append(section_id)
        buckets[section_id].append(name)

    sections: list[dict[str, Any]] = []
    for section_id in bucket_order:
        fields = buckets[section_id]
        if not fields:
            continue
        sections.append(
            {
                "id": section_id,
                "title_key": _section_title_key(type_id, section_id, catalog_kind=catalog_kind),
                "fields": fields,
            }
        )

    timing = [f for f in field_names if f in _TIMING_FIELDS]
    if timing:
        sections.append(
            {
                "id": "timing",
                "title_key": "ui.section.timing",
                "fields": timing,
            }
        )
    return sections


def _validate_presets(cls: type[BaseModel], type_id: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Validate clip_presets against model_fields and Pydantic coercion. Returns (valid_presets, warnings)."""
    raw = getattr(cls, "clip_presets", None)
    if not raw:
        return [], []

    valid: list[dict[str, Any]] = []
    warnings: list[str] = []
    known_fields = set(cls.model_fields.keys())
    defaults = {n: f.default for n, f in cls.model_fields.items() if f.default is not None}

    for preset in raw:
        pid = preset.get("id", "<unnamed>")
        values = preset.get("values", {})

        # Check field names
        unknown_keys = set(values.keys()) - known_fields
        if unknown_keys:
            warnings.append(
                f"{type_id}.preset.{pid}: unknown field(s) {sorted(unknown_keys)} — skipped"
            )
            continue

        # Pydantic coercion check
        try:
            cls.model_validate({**defaults, "id": "__preset_check__", **values})
        except Exception as exc:
            warnings.append(f"{type_id}.preset.{pid}: validation failed ({exc}) — skipped")
            continue

        valid.append(
            {
                "id": pid,
                "label_key": f"preset.{type_id}.{pid}",
                "values": values,
            }
        )

    return valid, warnings


def _plugin_type_id(cls: type) -> str:
    for attr in ("clip_type", "effect_type", "setting_type"):
        val = getattr(cls, attr, None)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _ui_entry_for_type_class(
    cls: type[BaseModel],
    *,
    catalog_kind: str = NLS_KIND_CLIP,
) -> tuple[str, dict[str, Any], list[str], list[str]]:
    type_id: str = _plugin_type_id(cls)
    if not type_id:
        return "", {}, [], []

    controls, unknowns, step_warnings = _build_controls_for_class(cls, catalog_kind=catalog_kind)
    presets, preset_warnings = _validate_presets(cls, type_id)
    stock_warnings = _validate_stock_attribution_fields(cls)
    step_warnings = list(step_warnings) + preset_warnings + stock_warnings
    entry: dict[str, Any] = {
        "schema_version": _SCHEMA_VERSION,
        "custom_ui": None,
        "sections": _build_sections(type_id, cls, catalog_kind=catalog_kind),
        "controls": controls,
    }
    if presets:
        entry["presets"] = presets
    return type_id, entry, unknowns, step_warnings


def _generate_ui_doc(
    plugin_class: Any,
) -> tuple[dict[str, Any], dict[str, list[str]], list[str]]:
    """Build the generated UI document, unknown fields, and step warnings."""
    doc: dict[str, Any] = {}
    unknown_report: dict[str, list[str]] = {}
    step_warnings: list[str] = []

    for type_cls in plugin_clip_types(plugin_class):
        nt, entry, unk, step_warns = _ui_entry_for_type_class(type_cls, catalog_kind=NLS_KIND_CLIP)
        if nt:
            doc[nt] = entry
            if unk:
                unknown_report[nt] = unk
            for w in step_warns:
                step_warnings.append(f"{nt}.{w}")

    for cfg_cls in getattr(plugin_class, "project_settings", []):
        nt, entry, unk, step_warns = _ui_entry_for_type_class(
            cfg_cls, catalog_kind=NLS_KIND_SETTING
        )
        if nt:
            doc[nt] = entry
            if unk:
                unknown_report[nt] = unk
            for w in step_warns:
                step_warnings.append(f"{nt}.{w}")

    for effect_cls in getattr(plugin_class, "effects", []) or []:
        nt, entry, unk, step_warns = _ui_entry_for_type_class(
            effect_cls, catalog_kind=NLS_KIND_EFFECT
        )
        if nt:
            doc[nt] = entry
            if unk:
                unknown_report[nt] = unk
            for w in step_warns:
                step_warnings.append(f"{nt}.{w}")

    return doc, unknown_report, step_warnings


def gen_ui(
    plugin_path: Annotated[
        Path, typer.Argument(help="Plugin root directory (must contain pyproject.toml)")
    ],
    check: Annotated[
        bool,
        typer.Option(
            "--check",
            help="Exit with code 1 if any field maps to kind=unknown (needs overrides or schema fix).",
        ),
    ] = False,
) -> None:
    """Generate schema.ui.generated.json and bootstrap schema.ui.overrides.json.

    The web (or API merge step) should combine ``schema.ui.generated.json`` with
    ``schema.ui.overrides.json``, with overrides winning. Re-run this command after
    changing clip fields; it always overwrites the generated file only.
    """
    plugin_root = plugin_path.resolve()
    console.print(f"Loading plugin from [bold]{plugin_root}[/bold] ...")
    try:
        plugin_class, package_dir = _load_plugin(plugin_root)
    except Exception as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1) from None

    manifest = plugin_class.manifest
    project_setting_count = len(getattr(plugin_class, "project_settings", []))
    effect_count = len(getattr(plugin_class, "effects", []) or [])
    console.print(
        f"  [dim]{manifest.display_name} — {len(plugin_clip_types(plugin_class))} clip type(s), "
        f"{project_setting_count} project setting(s), {effect_count} effect(s)[/dim]"
    )

    doc, unknown_report, step_warnings = _generate_ui_doc(plugin_class)

    gen_path = package_dir / "schema.ui.generated.json"
    ovr_path = package_dir / "schema.ui.overrides.json"

    gen_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    console.print(f"[green]OK[/green] Wrote {gen_path.name} ({len(doc)} type(s))")

    if not ovr_path.exists():
        ovr_path.write_text("{}\n", encoding="utf-8")
        console.print(
            f"[green]OK[/green] Created {ovr_path.name} (empty — add manual overrides here)"
        )
    else:
        console.print(f"  [dim]Left existing {ovr_path.name} untouched[/dim]")

    # Report
    table = Table(title="UI mapping coverage", show_lines=False)
    table.add_column("type_id", style="bold")
    table.add_column("fields", justify="right")
    table.add_column("unknown", justify="right")
    table.add_column("Status", justify="center")

    has_unknown = False
    for nt in sorted(doc.keys()):
        entry = doc[nt]
        n_fields = len(entry.get("controls", {}))
        unk = unknown_report.get(nt, [])
        n_unk = len(unk)
        if n_unk:
            has_unknown = True
            status = "[yellow]REVIEW[/yellow]"
            unk_cell = f"[yellow]{n_unk}[/yellow]"
        else:
            status = "[green]OK[/green]"
            unk_cell = "0"
        table.add_row(nt, str(n_fields), unk_cell, status)

    console.print(table)

    if unknown_report:
        console.print("[yellow]Unknown controls[/yellow] (add overrides or improve inference):")
        for nt, fields in sorted(unknown_report.items()):
            detail = doc[nt]["controls"]
            reasons = {f: detail[f].get("reason", "?") for f in fields}
            console.print(f"  [bold]{nt}[/bold]: {', '.join(fields)}  [dim]{reasons}[/dim]")

    if step_warnings:
        console.print("[yellow]Warnings[/yellow]:")
        for line in step_warnings[:40]:
            console.print(f"  [dim]{line}[/dim]")
        if len(step_warnings) > 40:
            console.print(f"  [dim]… and {len(step_warnings) - 40} more[/dim]")

    if check and has_unknown:
        console.print("[red]gen-ui --check failed:[/red] unknown control(s) remain.")
        raise typer.Exit(1)
