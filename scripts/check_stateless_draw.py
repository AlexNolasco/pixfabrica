#!/usr/bin/env python3
"""Static check: enforce the stateless draw() contract.

The contract (see plugins/README.md and VisualClip docstring) forbids any
cross-frame state on a clip instance: draw(ctx) must be a pure function of
self (post-prepare), ctx.time.frame, ctx.bounds, ctx.canvas, and
ctx.audio_bus_frame. The parallel renderer ships frames out of order to N
worker processes, so any mutation of self.* inside draw() silently corrupts
output (jumpy bars, mis-aligned scrolls, lost beats, etc.).

This walker flags every assignment to ``self.<attr>`` (including augmented
assignment, indexed assignment, tuple-targets, etc.) and every mutating
method call on ``self.<attr>`` (``.append``, ``.update``, ``.clear``, …)
that appears inside a ``def draw(self, ...)`` body.

The single allowed exception is the lazy-init pattern:

    if self._program is None:
        self._program = gl.program(...)
        self._vao     = gl.simple_vertex_array(...)

GL/Skia objects must be created against the live context at first draw,
because PrepareContext does not own that context. Anything written inside
``if self._X is None:`` is treated as idempotent setup, not per-frame state.

Exit code:
    0 — no offenders found
    1 — at least one offender found
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SCAN_ROOTS = ("plugins", "core")

MUTATING_METHODS = frozenset(
    {
        "append",
        "appendleft",
        "add",
        "clear",
        "discard",
        "extend",
        "insert",
        "pop",
        "popitem",
        "popleft",
        "remove",
        "reverse",
        "rotate",
        "setdefault",
        "sort",
        "update",
    }
)


def _underlying_self_attr(node: ast.AST) -> ast.Attribute | None:
    """If *node* ultimately roots in ``self.<attr>``, return the outermost
    ``self.X`` Attribute. Walks through Subscript and nested Attribute so we
    catch ``self._foo[i] = …`` and ``self._foo.bar = …`` alike.
    """
    cur: ast.AST = node
    while True:
        if isinstance(cur, ast.Attribute):
            if isinstance(cur.value, ast.Name) and cur.value.id == "self":
                return cur
            cur = cur.value
        elif isinstance(cur, ast.Subscript):
            cur = cur.value
        else:
            return None


def _is_none_guard(test: ast.AST) -> str | None:
    """Return the attr name if *test* is ``self.<attr> is None``, else None.

    This is the gate for the lazy-init exception.
    """
    if not isinstance(test, ast.Compare):
        return None
    if len(test.ops) != 1 or not isinstance(test.ops[0], ast.Is):
        return None
    if len(test.comparators) != 1:
        return None
    rhs = test.comparators[0]
    if not (isinstance(rhs, ast.Constant) and rhs.value is None):
        return None
    a = _underlying_self_attr(test.left)
    return a.attr if a is not None else None


def _guarded_ranges(fn: ast.FunctionDef) -> list[tuple[int, int]]:
    """Collect line ranges of ``if self.X is None:`` bodies inside *fn*."""
    ranges: list[tuple[int, int]] = []
    for node in ast.walk(fn):
        if isinstance(node, ast.If) and _is_none_guard(node.test) is not None and node.body:
            start = node.body[0].lineno
            end = node.body[-1].end_lineno or start
            ranges.append((start, end))
    return ranges


def _is_draw_method(node: ast.AST) -> bool:
    if not isinstance(node, ast.FunctionDef):
        return False
    if node.name != "draw":
        return False
    if not node.args.args:
        return False
    return node.args.args[0].arg == "self"


def _scan_draw(fn: ast.FunctionDef) -> list[tuple[int, int, str]]:
    guarded = _guarded_ranges(fn)

    def in_guard(line: int) -> bool:
        return any(s <= line <= e for s, e in guarded)

    findings: list[tuple[int, int, str]] = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                # Walk tuple/list targets: `self.a, x = ...`
                targets = tgt.elts if isinstance(tgt, ast.Tuple | ast.List) else [tgt]
                for t in targets:
                    a = _underlying_self_attr(t)
                    if a is not None and not in_guard(t.lineno):
                        findings.append(
                            (
                                t.lineno,
                                t.col_offset,
                                f"assignment to `self.{a.attr}` inside draw()",
                            )
                        )
        elif isinstance(node, ast.AugAssign):
            a = _underlying_self_attr(node.target)
            if a is not None and not in_guard(node.target.lineno):
                findings.append(
                    (
                        node.target.lineno,
                        node.target.col_offset,
                        f"augmented assignment to `self.{a.attr}` inside draw()",
                    )
                )
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            a = _underlying_self_attr(node.target)
            if a is not None and not in_guard(node.target.lineno):
                findings.append(
                    (
                        node.target.lineno,
                        node.target.col_offset,
                        f"annotated assignment to `self.{a.attr}` inside draw()",
                    )
                )
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in MUTATING_METHODS
        ):
            a = _underlying_self_attr(node.func.value)
            if a is not None and not in_guard(node.lineno):
                findings.append(
                    (
                        node.lineno,
                        node.col_offset,
                        f"mutating call `self.{a.attr}.{node.func.attr}(...)` inside draw()",
                    )
                )
    return findings


def _check_file(path: Path) -> list[tuple[Path, int, int, str]]:
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []

    results: list[tuple[Path, int, int, str]] = []
    for node in ast.walk(tree):
        if _is_draw_method(node):
            assert isinstance(node, ast.FunctionDef)
            for ln, col, msg in _scan_draw(node):
                results.append((path, ln, col, msg))
    return results


def main() -> int:
    findings: list[tuple[Path, int, int, str]] = []
    for root_name in SCAN_ROOTS:
        root = REPO_ROOT / root_name
        if not root.exists():
            continue
        for p in root.rglob("*.py"):
            # Skip vendored / generated / cache dirs.
            parts = set(p.parts)
            if "__pycache__" in parts or ".venv" in parts or "site-packages" in parts:
                continue
            findings.extend(_check_file(p))

    if not findings:
        print("OK — no stateful draw() mutations found")
        return 0

    findings.sort(key=lambda f: (str(f[0]), f[1], f[2]))
    for path, line, col, msg in findings:
        rel = path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path
        print(f"{rel}:{line}:{col}: {msg}")
    print()
    print(f"Found {len(findings)} violation(s) of the stateless draw() contract.")
    print("See plugins/README.md → 'Stateless draw() contract' for the fix pattern.")
    print("Allowed exception: `if self._X is None: self._X = ...` (lazy GL/Skia init).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
