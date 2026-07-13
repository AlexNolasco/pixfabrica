from __future__ import annotations

import importlib
import json
import re
import sys
import tomllib
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

from pixfabrica_cli.graph_enum_schema import enum_class_from_annotation
from pixfabrica_cli.literal_schema import (
    literal_display_en,
    literal_label_key_prefix,
    literal_tuple_from_annotation,
    literal_wire_slug,
)
from pixfabrica_core.clips import Clip
from pixfabrica_core.nls_keys import (
    NLS_KIND_CLIP,
    NLS_KIND_EFFECT,
    NLS_KIND_SETTING,
    nls_description_key,
    nls_field_description_key,
    nls_field_label_key,
    nls_label_key,
)
from pixfabrica_core.plugins import plugin_clip_types

console = Console()

_OLLAMA_BASE = "http://localhost:11434"

_LANG_NAMES: dict[str, str] = {
    "es": "Spanish (Latin American)",
    "ja": "Japanese",
    "zh-CN": "Simplified Chinese",
}

# Fields defined on Clip itself — not plugin-specific, excluded from NLS.
_BASE_FIELD_NAMES: frozenset[str] = frozenset()


def _plugin_type_id(cls: type) -> str:
    for attr in ("clip_type", "effect_type", "setting_type"):
        val = getattr(cls, attr, None)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _base_fields() -> frozenset[str]:
    global _BASE_FIELD_NAMES
    if not _BASE_FIELD_NAMES:
        _BASE_FIELD_NAMES = frozenset(Clip.model_fields.keys())
    return _BASE_FIELD_NAMES


# Fields defined on ProjectSetting itself — excluded from NLS.
_BASE_CONFIG_FIELD_NAMES: frozenset[str] = frozenset()


def _base_config_fields() -> frozenset[str]:
    global _BASE_CONFIG_FIELD_NAMES
    if not _BASE_CONFIG_FIELD_NAMES:
        from pixfabrica_core.composition.config import ProjectSetting

        _BASE_CONFIG_FIELD_NAMES = frozenset(ProjectSetting.model_fields.keys())
    return _BASE_CONFIG_FIELD_NAMES


# ── Prompts ──────────────────────────────────────────────────────────────────

_LABEL_PROMPT = """\
You are naming clip and effect types in a video compositor timeline UI.
For each entry below, produce a concise human-readable label (1–3 words, Title Case).
The key is the type's internal ID; the value is its docstring.

Input:
{input_json}

Rules:
- Return ONLY a valid JSON object mapping each key to its label string.
- No markdown fences, no commentary — raw JSON only.
- Labels must be short and clear for display in a UI panel.
"""

_TRANSLATE_PROMPT = """\
Translate the JSON values below from English to {lang_name}.
These are UI labels and descriptions for a timeline-based video compositor editor.

Input:
{input_json}

Rules:
- Return ONLY a valid JSON object with the same keys, translated values.
- No markdown fences, no commentary — raw JSON only.
- Do not translate the proper noun "Pixfabrica".
- Keep translations concise; they appear in a compact UI panel.
"""


# ── Helpers ───────────────────────────────────────────────────────────────────


def _humanize(name: str) -> str:
    return " ".join(w.capitalize() for w in name.split("_"))


def _field_label(field_name: str, field_info: Any) -> str:
    extra = field_info.json_schema_extra
    if isinstance(extra, dict):
        label = extra.get("label")
        if isinstance(label, str) and label.strip():
            return label.strip()
    return _humanize(field_name)


def _clean_docstring(cls: type) -> str:
    doc = (cls.__doc__ or "").strip()
    first_para = doc.split("\n\n")[0]
    return " ".join(first_para.split())


def _load_plugin(plugin_root: Path) -> tuple[Any, Path]:
    """Read pyproject.toml, inject src/ into sys.path, import Plugin, return (Plugin, package_dir)."""
    toml_path = plugin_root / "pyproject.toml"
    if not toml_path.exists():
        raise FileNotFoundError(f"No pyproject.toml at {plugin_root}")

    with open(toml_path, "rb") as f:
        toml = tomllib.load(f)

    package_name: str = toml.get("project", {}).get("name", plugin_root.name)
    module_name = package_name.replace("-", "_")

    src_path = plugin_root / "src"
    inject_path = src_path if src_path.exists() else plugin_root
    if str(inject_path) not in sys.path:
        sys.path.insert(0, str(inject_path))

    module = importlib.import_module(module_name)
    plugin_class = module.Plugin
    package_dir = inject_path / module_name
    return plugin_class, package_dir


def _enum_option_nls_key(enum_cls: type, wire: str) -> str:
    """NLS key for one enum wire value (stable for StrEnum / IntEnum payloads)."""
    safe = str(wire).replace(".", "_")
    return f"enum.{enum_cls.__name__}.{safe}"


def _add_literal_strings(
    strings: dict[str, str],
    type_id: str,
    field_name: str,
    field_info: Any,
    *,
    catalog_kind: str = NLS_KIND_CLIP,
) -> None:
    lit = literal_tuple_from_annotation(field_info.annotation)
    if not lit:
        return
    prefix = literal_label_key_prefix(type_id, field_name, catalog_kind=catalog_kind)
    for v in lit:
        key = f"{prefix}.{literal_wire_slug(v)}"
        strings[key] = literal_display_en(v) if isinstance(v, str) else str(v)


def _add_enum_strings(strings: dict[str, str], field_info: Any) -> None:
    enum_cls = enum_class_from_annotation(field_info.annotation)
    if enum_cls is None:
        return
    for member in enum_cls:
        key = _enum_option_nls_key(enum_cls, str(member.value))
        strings[key] = _humanize(member.name)


def _extract_strings_for_type_classes(
    strings: dict[str, str],
    classes: list[type],
    *,
    skip_fields: frozenset[str],
    include_presets: bool,
    catalog_kind: str = NLS_KIND_CLIP,
) -> None:
    for type_cls in classes:
        type_id: str = _plugin_type_id(type_cls)
        if not type_id:
            continue

        doc = _clean_docstring(type_cls)
        if doc:
            strings[nls_description_key(type_id, catalog_kind=catalog_kind)] = doc

        for field_name, field_info in type_cls.model_fields.items():
            if field_name in skip_fields:
                continue
            strings[nls_field_label_key(type_id, field_name, catalog_kind=catalog_kind)] = (
                _field_label(field_name, field_info)
            )
            if field_info.description:
                strings[
                    nls_field_description_key(type_id, field_name, catalog_kind=catalog_kind)
                ] = field_info.description
            _add_enum_strings(strings, field_info)
            _add_literal_strings(
                strings, type_id, field_name, field_info, catalog_kind=catalog_kind
            )

        if include_presets:
            for preset in getattr(type_cls, "clip_presets", []):
                pid = preset.get("id")
                label = preset.get("label")
                if pid and label:
                    strings[f"preset.{type_id}.{pid}"] = label


def _extract_english(plugin_class: Any) -> dict[str, str]:
    """Build English strings from Python metadata (deterministic, no Ollama)."""
    base = _base_fields()
    base_config = _base_config_fields()
    manifest = plugin_class.manifest

    strings: dict[str, str] = {
        "plugin.display_name": manifest.display_name,
        "plugin.description": manifest.description,
        "ui.control.color_stop_list.item": "Color stop",
        "ui.control.color_list.item": "Color",
    }

    _extract_strings_for_type_classes(
        strings,
        plugin_clip_types(plugin_class),
        skip_fields=base,
        include_presets=True,
        catalog_kind=NLS_KIND_CLIP,
    )
    _extract_strings_for_type_classes(
        strings,
        getattr(plugin_class, "project_settings", []),
        skip_fields=base_config,
        include_presets=False,
        catalog_kind=NLS_KIND_SETTING,
    )
    _extract_strings_for_type_classes(
        strings,
        getattr(plugin_class, "effects", []) or [],
        skip_fields=base,
        include_presets=False,
        catalog_kind=NLS_KIND_EFFECT,
    )

    return strings


_UI_SECTION_DEFAULTS: dict[str, str] = {
    "parameters": "Parameters",
    "timing": "Timing",
}


def _default_ui_section_label(section_id: str) -> str:
    if section_id in _UI_SECTION_DEFAULTS:
        return _UI_SECTION_DEFAULTS[section_id]
    return _humanize(section_id)


def _extract_ui_section_strings(
    package_dir: Path,
    strings: dict[str, str],
    existing_en: dict[str, str],
) -> None:
    """Add Properties section title keys from schema.ui.generated.json."""
    ui_path = package_dir / "schema.ui.generated.json"
    if not ui_path.is_file():
        return

    try:
        ui_spec = json.loads(ui_path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        console.print(
            "[yellow]Warning:[/yellow] Could not parse schema.ui.generated.json — skipping section titles"
        )
        return

    if not isinstance(ui_spec, dict):
        return

    for type_ui in ui_spec.values():
        if not isinstance(type_ui, dict):
            continue
        sections = type_ui.get("sections")
        if not isinstance(sections, list):
            continue
        for sec in sections:
            if not isinstance(sec, dict):
                continue
            title_key_raw = sec.get("title_key")
            if not isinstance(title_key_raw, str):
                continue
            title_key = title_key_raw.strip()
            if not title_key:
                continue
            if title_key in existing_en:
                strings[title_key] = existing_en[title_key]
                continue
            if title_key in strings:
                continue
            sec_id = sec.get("id")
            section_id = sec_id.strip() if isinstance(sec_id, str) else ""
            strings[title_key] = _default_ui_section_label(section_id)


def _sorted_strings(strings: dict[str, str]) -> dict[str, str]:
    """Sort keys: plugin.* first, then grouped by catalog type."""

    def _key(k: str) -> tuple[int, str]:
        if k.startswith("plugin."):
            return (0, k)
        return (1, k)

    return {k: strings[k] for k in sorted(strings, key=_key)}


# ── Ollama calls ──────────────────────────────────────────────────────────────


def _call_ollama(prompt: str, model: str) -> str:
    import httpx

    with httpx.Client(timeout=120.0) as client:
        resp = client.post(
            f"{_OLLAMA_BASE}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
        )
        resp.raise_for_status()
        return resp.json()["response"]


def _parse_json_response(raw: str) -> dict[str, str]:
    text = raw.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        text = match.group(1).strip()
    return json.loads(text)


def _type_catalog_kinds(plugin_class: Any) -> dict[str, str]:
    kinds: dict[str, str] = {}
    for cls in plugin_clip_types(plugin_class):
        clip_type = getattr(cls, "clip_type", None)
        if isinstance(clip_type, str) and clip_type.strip():
            kinds[clip_type.strip()] = NLS_KIND_CLIP
    for cls in getattr(plugin_class, "project_settings", []):
        type_id = _plugin_type_id(cls)
        if type_id:
            kinds[type_id] = NLS_KIND_SETTING
    for cls in getattr(plugin_class, "effects", []) or []:
        type_id = _plugin_type_id(cls)
        if type_id:
            kinds[type_id] = NLS_KIND_EFFECT
    return kinds


def _get_type_labels(
    plugin_class: Any,
    missing_types: set[str],
    model: str,
    type_kinds: dict[str, str],
) -> tuple[dict[str, str], int]:
    """One Ollama call to generate short UI labels for the given catalog types.

    Returns (labels, fallback_count) where fallback_count > 0 means Ollama failed
    and humanized fallbacks were used instead.
    """
    all_type_classes = (
        list(plugin_clip_types(plugin_class))
        + list(getattr(plugin_class, "project_settings", []))
        + list(getattr(plugin_class, "effects", []) or [])
    )
    type_info = {
        _plugin_type_id(cls): _clean_docstring(cls)
        for cls in all_type_classes
        if _plugin_type_id(cls) in missing_types
    }
    prompt = _LABEL_PROMPT.format(input_json=json.dumps(type_info, ensure_ascii=False, indent=2))
    try:
        raw = _call_ollama(prompt, model)
        result = _parse_json_response(raw)
        return (
            {
                nls_label_key(k, catalog_kind=type_kinds.get(k, NLS_KIND_EFFECT)): v
                for k, v in result.items()
                if k in missing_types
            },
            0,
        )
    except Exception as exc:
        console.print(
            f"  [yellow]Warning:[/yellow] label generation failed ({exc}); using fallback"
        )
        return (
            {
                nls_label_key(t, catalog_kind=type_kinds.get(t, NLS_KIND_EFFECT)): _humanize(
                    t.split("-", 1)[-1] if "-" in t else t
                )
                for t in missing_types
            },
            len(missing_types),
        )


_CHUNK_SIZE = 50  # keys per Ollama call — stays comfortably within any model's context window


def _translate(strings: dict[str, str], lang: str, model: str) -> dict[str, str]:
    lang_name = _LANG_NAMES.get(lang, lang)
    items = list(strings.items())
    chunks = [dict(items[i : i + _CHUNK_SIZE]) for i in range(0, len(items), _CHUNK_SIZE)]

    result: dict[str, str] = {}
    for chunk in chunks:
        prompt = _TRANSLATE_PROMPT.format(
            lang_name=lang_name,
            input_json=json.dumps(chunk, ensure_ascii=False, indent=2),
        )
        try:
            raw = _call_ollama(prompt, model)
            translated = _parse_json_response(raw)
            # Only keep keys that were in this chunk — drop any hallucinated keys.
            result.update({k: v for k, v in translated.items() if k in chunk})
        except Exception as exc:
            console.print(
                f"  [yellow]Warning:[/yellow] translation chunk to {lang} failed ({exc}); skipping chunk"
            )
    return result


# ── Command ───────────────────────────────────────────────────────────────────


def gen_nls(
    plugin_path: Annotated[
        Path, typer.Argument(help="Plugin root directory (must contain pyproject.toml)")
    ],
    model: Annotated[str, typer.Option("--model", help="Ollama model name")] = "qwen2.5:14b",
    lang: Annotated[
        str,
        typer.Option(
            "--lang",
            help="Comma-separated language codes to translate this run; other locales in the file are kept (pruned to current en keys)",
        ),
    ] = "es,ja,zh-CN",
    force: Annotated[
        bool,
        typer.Option("--force", help="Wipe existing non-English translations and regenerate"),
    ] = False,
) -> None:
    """Generate or update schema.nls.json for a plugin using Ollama for translations."""
    plugin_root = plugin_path.resolve()
    target_langs = [c.strip() for c in lang.split(",") if c.strip()]

    # 1. Load plugin
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

    nls_path = package_dir / "schema.nls.json"

    # 2. Load existing NLS
    existing: dict[str, dict[str, str]] = {}
    if nls_path.exists():
        try:
            existing = json.loads(nls_path.read_text("utf-8"))
            console.print(f"  Found existing {nls_path.name}")
        except Exception:
            console.print(
                "[yellow]Warning:[/yellow] Could not parse existing schema.nls.json — starting fresh"
            )

    existing_en = existing.get("en", {})

    # 3. Extract deterministic English strings
    en_strings = _extract_english(plugin_class)
    _extract_ui_section_strings(package_dir, en_strings, existing_en)

    # 4. Generate type labels (Ollama) for any type missing a label
    type_kinds = _type_catalog_kinds(plugin_class)
    missing_label_types: set[str] = set()
    for type_id, catalog_kind in type_kinds.items():
        label_key = nls_label_key(type_id, catalog_kind=catalog_kind)
        if not force and label_key in existing_en:
            en_strings[label_key] = existing_en[label_key]
            continue
        missing_label_types.add(type_id)

    label_fallback_count = 0
    if missing_label_types:
        console.print(
            f"Generating labels for {len(missing_label_types)} type(s) via Ollama [dim]({model})[/dim] ..."
        )
        labels, label_fallback_count = _get_type_labels(
            plugin_class, missing_label_types, model, type_kinds
        )
        en_strings.update(labels)

    en_strings = _sorted_strings(en_strings)

    # 5. Build result dict.
    # Always discard lang keys that are no longer in en (orphaned fields / old hallucinations).
    # --force additionally wipes all existing translations to force a full re-translate.
    result: dict[str, dict[str, str]] = {"en": en_strings}
    for lang_code in target_langs:
        if force:
            result[lang_code] = {}
        else:
            result[lang_code] = {
                k: v for k, v in existing.get(lang_code, {}).items() if k in en_strings
            }

    # 6. Translate missing keys per language
    for lang_code in target_langs:
        lang_section = result[lang_code]
        missing = {k: v for k, v in en_strings.items() if k not in lang_section}
        if missing:
            console.print(
                f"Translating {len(missing)} key(s) to [bold]{lang_code}[/bold] [dim]({model})[/dim] ..."
            )
            translated = _translate(missing, lang_code, model)
            if translated:
                lang_section.update(translated)
                result[lang_code] = _sorted_strings(lang_section)
        else:
            console.print(
                f"  [dim]{lang_code}: all {len(lang_section)} key(s) present — skipping[/dim]"
            )

    # 6b. Keep locales already in schema.nls.json that are not in --lang (pruned to current en keys).
    for lang_code, section in existing.items():
        if lang_code == "en" or lang_code in target_langs or not isinstance(section, dict):
            continue
        result[lang_code] = _sorted_strings({k: v for k, v in section.items() if k in en_strings})

    # 7. Write
    nls_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    console.print(f"[green]OK[/green] Wrote {nls_path}")

    # 8. Report
    table = Table(title="NLS Coverage", show_lines=False)
    table.add_column("Language", style="bold")
    table.add_column("Expected", justify="right")
    table.add_column("Translated", justify="right")
    table.add_column("Missing", justify="right")
    table.add_column("Status", justify="center")

    en_key_set = set(en_strings)
    has_gaps = False
    for lang_code in sorted(k for k in result if k != "en"):
        lang_key_set = set(result[lang_code])
        missing_keys = en_key_set - lang_key_set
        extra_keys = lang_key_set - en_key_set
        missing = len(missing_keys) + len(extra_keys)
        translated = len(lang_key_set)
        if missing > 0:
            has_gaps = True
            status = "[red]FAIL[/red]"
            missing_str = f"[red]{missing}[/red]"
        else:
            status = "[green]OK[/green]"
            missing_str = "0"
        table.add_row(lang_code, str(len(en_key_set)), str(translated), missing_str, status)

    console.print(table)

    if label_fallback_count > 0:
        console.print(
            f"[yellow]Warning:[/yellow] {label_fallback_count} type label(s) used humanized fallback"
        )

    if has_gaps:
        raise typer.Exit(1)
