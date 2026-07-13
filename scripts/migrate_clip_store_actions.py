#!/usr/bin/env python3
"""Rename element-prefixed store actions to clip-prefixed across web/src."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "web" / "src"

REPLACEMENTS = [
    ("addElement", "addClip"),
    ("updateElement", "updateClip"),
    ("removeElement", "removeClip"),
    ("duplicateElement", "duplicateClip"),
    ("moveElement", "moveClip"),
    ("reorderElements", "reorderClips"),
    ("swapTrackElements", "swapTrackClips"),
    ("toggleElementEnabled", "toggleClipEnabled"),
    ("insertElementCloneAfter", "insertClipCloneAfter"),
    ("applyClipPreset", "applyClipPreset"),
    ("frontElementId", "frontClipId"),
    ("afterElementId", "afterClipId"),
    ("// ---- Element actions", "// ---- Clip actions"),
    ("// ---- Job node actions", "// ---- Project setting actions"),
]

SKIP = {"scripts"}

for path in sorted(ROOT.rglob("*")):
    if path.suffix not in {".ts", ".tsx"}:
        continue
    if any(part in SKIP for part in path.parts):
        continue
    text = path.read_text(encoding="utf-8")
    original = text
    for old, new in REPLACEMENTS:
        text = text.replace(old, new)
    if text != original:
        path.write_text(text, encoding="utf-8")
        print(path.relative_to(ROOT.parent.parent))
