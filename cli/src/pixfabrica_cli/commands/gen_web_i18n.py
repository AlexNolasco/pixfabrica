"""Generate / update web UI strings (i18n.messages.json) using Ollama."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from pixfabrica_cli.commands.gen_nls import _LANG_NAMES, _call_ollama, _parse_json_response

console = Console()

_CHUNK_SIZE = 50

_WEB_TRANSLATE_PROMPT = """\
Translate the JSON values below from English to {lang_name}.
These are UI strings for a video compositor web app (menus, timeline, settings, properties).

Input:
{input_json}

Rules:
- Return ONLY a valid JSON object with the same keys, translated values.
- No markdown fences, no commentary — raw JSON only.
- Do not translate the proper noun "Pixfabrica".
- Preserve placeholders like {{n}} exactly (same braces and identifier).
- Keep translations concise; they appear in panels and toolbars.
"""


def _unescape_ts_single_quoted(raw: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(raw):
        if raw[i] == "\\" and i + 1 < len(raw):
            n = raw[i + 1]
            if n == "\\":
                out.append("\\")
            elif n == "'":
                out.append("'")
            elif n == "n":
                out.append("\n")
            elif n == "r":
                out.append("\r")
            elif n == "t":
                out.append("\t")
            else:
                out.append(n)
            i += 2
            continue
        out.append(raw[i])
        i += 1
    return "".join(out)


_KV_PAIR = re.compile(r"([a-zA-Z0-9_]+)\s*:\s*'((?:\\.|[^'\\])*)'")


def _parse_ts_kv_object_body(body: str) -> dict[str, str]:
    """Parse TS object literal body with `key: 'value'` entries (single-quoted values)."""
    out: dict[str, str] = {}
    for line in body.splitlines():
        code = line.split("//", 1)[0].strip()
        if not code:
            continue
        for m in _KV_PAIR.finditer(code):
            out[m.group(1)] = _unescape_ts_single_quoted(m.group(2))
    return out


def _skip_ts_single_quoted_string(s: str, i: int) -> int:
    assert s[i] == "'"
    i += 1
    while i < len(s):
        if s[i] == "\\":
            i += 2
            continue
        if s[i] == "'":
            return i + 1
        i += 1
    msg = "unterminated single-quoted string"
    raise ValueError(msg)


def _skip_line_comment(s: str, i: int) -> int:
    if i + 1 < len(s) and s[i : i + 2] == "//":
        nl = s.find("\n", i)
        return len(s) if nl == -1 else nl + 1
    return i


def _find_matching_brace(s: str, open_brace: int) -> int:
    depth = 0
    i = open_brace
    while i < len(s):
        i = _skip_line_comment(s, i)
        if i >= len(s):
            break
        c = s[i]
        if c == "'":
            i = _skip_ts_single_quoted_string(s, i)
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    msg = "unbalanced braces in TS object"
    raise ValueError(msg)


def _object_body_after_anchor(src: str, anchor_re: re.Pattern[str]) -> str:
    m = anchor_re.search(src)
    if not m:
        msg = f"anchor not found: {anchor_re.pattern!r}"
        raise ValueError(msg)
    brace = src.index("{", m.end() - 1)
    close = _find_matching_brace(src, brace)
    return src[brace + 1 : close]


def _legacy_extract_messages(i18n_ts: str) -> dict[str, dict[str, str]]:
    """Parse legacy web/src/lib/i18n.ts with inline const en / es / zhCN objects."""
    en_body = _object_body_after_anchor(
        i18n_ts,
        re.compile(r"const\s+en\s*=\s*\{"),
    )
    es_body = _object_body_after_anchor(
        i18n_ts,
        re.compile(r"const\s+es\s*:\s*Partial[^=]*=\s*\{"),
    )
    zh_body = _object_body_after_anchor(
        i18n_ts,
        re.compile(r"const\s+zhCN\s*:\s*Partial[^=]*=\s*\{"),
    )
    return {
        "en": _parse_ts_kv_object_body(en_body),
        "es": _parse_ts_kv_object_body(es_body),
        "zh-CN": _parse_ts_kv_object_body(zh_body),
    }


def _translate_web_chunked(strings: dict[str, str], lang: str, model: str) -> dict[str, str]:
    lang_name = _LANG_NAMES.get(lang, lang)
    items = list(strings.items())
    chunks = [dict(items[i : i + _CHUNK_SIZE]) for i in range(0, len(items), _CHUNK_SIZE)]
    result: dict[str, str] = {}
    for chunk in chunks:
        prompt = _WEB_TRANSLATE_PROMPT.format(
            lang_name=lang_name,
            input_json=json.dumps(chunk, ensure_ascii=False, indent=2),
        )
        try:
            raw = _call_ollama(prompt, model)
            translated = _parse_json_response(raw)
            result.update({k: v for k, v in translated.items() if k in chunk})
        except Exception as exc:
            console.print(
                f"  [yellow]Warning:[/yellow] translation chunk to {lang} failed ({exc}); skipping chunk"
            )
    return result


def _sorted_str_dict(d: dict[str, str]) -> dict[str, str]:
    return {k: d[k] for k in sorted(d)}


def gen_web_i18n(
    web_root: Annotated[
        Path,
        typer.Argument(
            help="Web package root (directory containing src/lib/)",
        ),
    ] = Path("web"),
    model: Annotated[str, typer.Option("--model", help="Ollama model name")] = "qwen2.5:14b",
    lang: Annotated[
        str,
        typer.Option(
            "--lang",
            help="Comma-separated language codes to translate; other locales in the JSON are kept (pruned to en keys)",
        ),
    ] = "es,zh-CN",
    force: Annotated[
        bool,
        typer.Option(
            "--force", help="Wipe existing translations for --lang locales and regenerate"
        ),
    ] = False,
) -> None:
    """Update web/src/lib/i18n.messages.json from English source strings (Ollama for targets)."""
    root = web_root.resolve()
    legacy_ts = root / "src/lib/i18n.ts"
    messages_path = root / "src/lib/i18n.messages.json"

    target_langs = [c.strip() for c in lang.split(",") if c.strip()]

    if messages_path.exists():
        existing: dict[str, dict[str, str]] = json.loads(
            messages_path.read_text(encoding="utf-8"),
        )
    elif legacy_ts.exists():
        console.print(
            f"[yellow]No[/yellow] {messages_path.name} - bootstrapping from legacy "
            f"[dim]{legacy_ts}[/dim] ..."
        )
        raw_ts = legacy_ts.read_text(encoding="utf-8")
        if "const en = {" not in raw_ts or "satisfies Record<string, string>" not in raw_ts:
            console.print(
                "[red]Error:[/red] legacy i18n.ts has no `const en = {` block; create i18n.messages.json manually."
            )
            raise typer.Exit(1)
        existing = _legacy_extract_messages(raw_ts)
        console.print(
            f"[dim]Bootstrapped in-memory from legacy i18n.ts ({len(existing['en'])} en keys)[/dim]"
        )
    else:
        console.print(
            f"[red]Error:[/red] neither {messages_path} nor {legacy_ts} exists under {root}"
        )
        raise typer.Exit(1)

    en_strings = existing.get("en") or {}
    if not isinstance(en_strings, dict) or not en_strings:
        console.print('[red]Error:[/red] messages.json must contain a non-empty "en" object')
        raise typer.Exit(1)
    en_strings = {str(k): str(v) for k, v in en_strings.items()}

    result: dict[str, dict[str, str]] = {"en": _sorted_str_dict(en_strings)}

    for lang_code in target_langs:
        if force:
            result[lang_code] = {}
        else:
            prev = existing.get(lang_code, {})
            if not isinstance(prev, dict):
                prev = {}
            result[lang_code] = {str(k): str(v) for k, v in prev.items() if k in en_strings}

    for lang_code in target_langs:
        lang_section = result[lang_code]
        missing = {k: v for k, v in en_strings.items() if k not in lang_section}
        if missing:
            console.print(
                f"Translating {len(missing)} key(s) to [bold]{lang_code}[/bold] [dim]({model})[/dim] ..."
            )
            translated = _translate_web_chunked(missing, lang_code, model)
            if translated:
                lang_section.update(translated)
                result[lang_code] = _sorted_str_dict(lang_section)
        else:
            console.print(
                f"  [dim]{lang_code}: all {len(lang_section)} key(s) present - skipping[/dim]"
            )

    for lang_code, section in existing.items():
        if lang_code == "en" or lang_code in target_langs or not isinstance(section, dict):
            continue
        result[lang_code] = _sorted_str_dict(
            {str(k): str(v) for k, v in section.items() if k in en_strings},
        )

    messages_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    console.print(f"[green]OK[/green] Wrote {messages_path}")

    table = Table(title="Web i18n coverage", show_lines=False)
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
        gap = len(missing_keys) + len(extra_keys)
        translated = len(lang_key_set)
        if gap > 0:
            has_gaps = True
            status = "[red]FAIL[/red]"
            missing_str = f"[red]{gap}[/red]"
        else:
            status = "[green]OK[/green]"
            missing_str = "0"
        table.add_row(lang_code, str(len(en_key_set)), str(translated), missing_str, status)

    console.print(table)

    if has_gaps:
        raise typer.Exit(1)
