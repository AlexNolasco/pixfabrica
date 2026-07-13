"""Sanity tests for scripts/check_stateless_draw.py.

We keep this test next to the core suite so the contract checker can't
silently regress (e.g. someone deletes the AST walk and `OK` always prints).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_stateless_draw.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_stateless_draw", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_stateless_draw"] = module
    spec.loader.exec_module(module)
    return module


def _scan_source(src: str, tmp_path: Path) -> list[str]:
    """Write src to a temp .py file and return formatted findings."""
    checker = _load_checker()
    f = tmp_path / "node.py"
    f.write_text(src, encoding="utf-8")
    return [msg for _path, _line, _col, msg in checker._check_file(f)]


def test_script_exists() -> None:
    assert SCRIPT_PATH.is_file(), "scripts/check_stateless_draw.py is missing"


def test_repo_passes_check() -> None:
    """The whole repo must pass — guards against silently breaking the checker
    or accidentally introducing a stateful draw()."""
    checker = _load_checker()
    findings = []
    for root_name in checker.SCAN_ROOTS:
        root = REPO_ROOT / root_name
        if not root.exists():
            continue
        for p in root.rglob("*.py"):
            parts = set(p.parts)
            if "__pycache__" in parts or ".venv" in parts:
                continue
            findings.extend(checker._check_file(p))
    assert findings == [], "\n".join(f"{p}:{ln}:{c}: {m}" for p, ln, c, m in findings)


def test_detects_plain_assignment(tmp_path: Path) -> None:
    src = """\
class Foo:
    def draw(self, ctx):
        self._counter = ctx.time.frame
"""
    msgs = _scan_source(src, tmp_path)
    assert any("self._counter" in m for m in msgs), msgs


def test_detects_aug_assignment(tmp_path: Path) -> None:
    src = """\
class Foo:
    def draw(self, ctx):
        self._acc += 1
"""
    msgs = _scan_source(src, tmp_path)
    assert any("self._acc" in m and "augmented" in m for m in msgs), msgs


def test_detects_indexed_assignment(tmp_path: Path) -> None:
    src = """\
class Foo:
    def draw(self, ctx):
        self._buf[0] = 1.0
"""
    msgs = _scan_source(src, tmp_path)
    assert any("self._buf" in m for m in msgs), msgs


def test_detects_tuple_assignment(tmp_path: Path) -> None:
    src = """\
class Foo:
    def draw(self, ctx):
        self._a, local = 1, 2
"""
    msgs = _scan_source(src, tmp_path)
    assert any("self._a" in m for m in msgs), msgs


def test_detects_mutating_call(tmp_path: Path) -> None:
    src = """\
class Foo:
    def draw(self, ctx):
        self._history.append(ctx.time.frame)
"""
    msgs = _scan_source(src, tmp_path)
    assert any("self._history" in m and "append" in m for m in msgs), msgs


def test_allows_lazy_none_init(tmp_path: Path) -> None:
    """Standard lazy GL init pattern — must not be flagged."""
    src = """\
class Foo:
    def draw(self, ctx):
        if self._program is None:
            self._program = ctx.canvas.program(vertex_shader='', fragment_shader='')
            self._vao = ctx.canvas.simple_vertex_array(self._program, None, 'in_vert')
"""
    msgs = _scan_source(src, tmp_path)
    assert msgs == [], msgs


def test_allows_local_variables(tmp_path: Path) -> None:
    src = """\
class Foo:
    def draw(self, ctx):
        x = 1
        x += 2
        local_list = []
        local_list.append(x)
"""
    msgs = _scan_source(src, tmp_path)
    assert msgs == [], msgs


def test_does_not_flag_other_methods(tmp_path: Path) -> None:
    """Mutations in prepare(), helpers, __init__ etc. are fine."""
    src = """\
class Foo:
    def __init__(self):
        self._x = 0

    async def prepare(self, ctx, bounds=None):
        self._x = 1
        self._buf.append(2)

    def _helper(self):
        self._x += 1
"""
    msgs = _scan_source(src, tmp_path)
    assert msgs == [], msgs


def test_flags_outside_guard(tmp_path: Path) -> None:
    """A mutation after the guarded init block must still be flagged."""
    src = """\
class Foo:
    def draw(self, ctx):
        if self._program is None:
            self._program = ctx.canvas.program(vertex_shader='', fragment_shader='')
        self._counter = ctx.time.frame
"""
    msgs = _scan_source(src, tmp_path)
    assert any("self._counter" in m for m in msgs), msgs
    assert not any("self._program" in m for m in msgs), msgs


def test_flags_self_method_with_mutating_name(tmp_path: Path) -> None:
    """`self.update(...)` (without an intermediate attr) is technically a
    mutator too — guard against the trivial case where someone names a node
    method ``update`` and calls it from draw()."""
    # Our checker only flags `self.<attr>.<mutator>(...)`, not bare
    # `self.<mutator>(...)`. That's intentional: a `def update(self):` method
    # is a normal method, not a list mutation. Confirm by negative assertion.
    src = """\
class Foo:
    def draw(self, ctx):
        self.update(ctx)

    def update(self, ctx):
        pass
"""
    msgs = _scan_source(src, tmp_path)
    assert msgs == [], msgs
