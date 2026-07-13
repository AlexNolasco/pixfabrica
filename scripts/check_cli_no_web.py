#!/usr/bin/env python3
"""Ensure the pixfabrica-cli package does not depend on or import the web/ SPA.

The web app is a separate TypeScript project (not a uv workspace member). The CLI
may still ship *maintenance* commands under ``pixfabrica web …`` that write into
``web/`` via explicit ``Path`` arguments — those modules are allowlisted below.

Exit code:
    0 — boundary intact
    1 — violation found
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CLI_ROOT = REPO_ROOT / "cli"
CLI_SRC = CLI_ROOT / "src" / "pixfabrica_cli"
CLI_PYPROJECT = CLI_ROOT / "pyproject.toml"

# Files allowed to mention web/ paths (SPA maintenance commands only).
_WEB_PATH_ALLOWLIST = frozenset(
    {
        "commands/gen_web_i18n.py",
        "commands/gen_typography.py",
        "commands/bake_preview_sample.py",
        "commands/bake_preview_samples.py",
        "commands/web.py",
    }
)

_FORBIDDEN_PYPROJECT_TOKENS = (
    "pixfabrica-web",
    '{ workspace = true, path = "web"',
    '{ path = "web"',
    'path = "../web"',
)


def _check_pyproject() -> list[str]:
    text = CLI_PYPROJECT.read_text(encoding="utf-8")
    issues: list[str] = []
    for token in _FORBIDDEN_PYPROJECT_TOKENS:
        if token in text:
            issues.append(f"cli/pyproject.toml must not reference web workspace: found {token!r}")
    if re.search(r'^\s*"?web"?\s*=\s*\{', text, re.MULTILINE):
        issues.append("cli/pyproject.toml must not declare a uv source for web")
    return issues


def _is_forbidden_web_import(module: str | None) -> bool:
    if not module:
        return False
    return module == "web" or module.startswith("web.")


def _path_args_target_web(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    is_path = isinstance(func, ast.Name) and func.id == "Path"
    is_path_attr = (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Name)
        and func.value.id == "Path"
    )
    if not (is_path or is_path_attr):
        return False
    if not node.args:
        return False
    first = node.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        val = first.value.replace("\\", "/")
        return val == "web" or val.startswith("web/")
    return False


def _check_python_file(path: Path) -> list[str]:
    rel = path.relative_to(CLI_SRC).as_posix()
    allow_web_paths = rel in _WEB_PATH_ALLOWLIST
    issues: list[str] = []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom, ast.Call)):
            continue
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_forbidden_web_import(alias.name):
                    issues.append(f"{rel}:{line}: forbidden import {alias.name!r}")
        elif isinstance(node, ast.ImportFrom):
            if _is_forbidden_web_import(node.module):
                issues.append(f"{rel}:{line}: forbidden import from {node.module!r}")
        elif not allow_web_paths and _path_args_target_web(node):
            issues.append(f"{rel}:{line}: Path(...) targets web/ outside allowlist")

    return issues


def main() -> int:
    issues = _check_pyproject()
    for py_file in sorted(CLI_SRC.rglob("*.py")):
        issues.extend(_check_python_file(py_file))

    if not issues:
        print("OK — cli package does not reference web/")
        return 0

    print("CLI ↔ web boundary violations:", file=sys.stderr)
    for issue in issues:
        print(f"  {issue}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
