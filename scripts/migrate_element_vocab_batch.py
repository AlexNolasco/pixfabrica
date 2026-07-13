#!/usr/bin/env python3
"""Batch-rename timeline element vocabulary to clip in Python/TS sources."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SKIP_BASENAMES = {
    "migrate_element_vocab_batch.py",
    "migrate_element_type_to_clip.py",
    "migrate_clip_store_actions.py",
    "migrate_selection_kind.py",
}

SKIP_GLOBS = (
    "**/schema.nls.json",
    "**/schema.ui.generated.json",
    "**/node_modules/**",
    "**/dist/**",
    "**/.pytest_cache/**",
)

# Longest-first identifier renames (whole word).
IDENT_RENAMES: list[tuple[str, str]] = [
    ("render_skia_element_with_effects", "render_skia_clip_with_effects"),
    ("render_gl_element_with_effects", "render_gl_clip_with_effects"),
    ("visual_element_needs_effect_pipeline", "visual_clip_needs_effect_pipeline"),
    ("_render_active_track_elements", "_render_active_track_clips"),
    ("_unknown_element_types", "_unknown_clip_types"),
    ("unknown_element_types", "unknown_clip_types"),
    ("_element_active_at", "_clip_active_at"),
    ("_dump_element", "_dump_clip"),
    ("_element_clip_type", "_clip_type_of"),
    ("_is_text_element", "_is_text_clip"),
    ("_element_offsets", "_clip_offsets"),
    ("_element_time_range", "_clip_time_range"),
    ("_merge_element", "_merge_clip"),
    ("text_elements", "text_clips"),
    ("hero_elements", "hero_clips"),
    ("lint_typography_roles(text_clips", "lint_typography_roles(text_clips"),  # noop guard
    ("elementDragId", "clipDragId"),
    ("elementTrackKind", "clipTrackKind"),
    ("elementNeedsBusPreview", "clipNeedsBusPreview"),
    ("elementPreviewWebSocketUrl", "clipPreviewWebSocketUrl"),
    ("elementPreviewClient", "clipPreviewClient"),
    ("requestElementPreviewFromStore", "requestClipPreviewFromStore"),
    ("elementPreviewPayload", "clipPreviewPayload"),
    ("elementPreviewRefresh", "clipPreviewRefresh"),
    ("elementPreviewAudio", "clipPreviewAudio"),
    ("elementPreviewMode", "clipPreviewMode"),
    ("elementParamsExport", "clipParamsExport"),
    ("elementParamsImport", "clipParamsImport"),
    ("brokenNodesFingerprint", "brokenClipsFingerprint"),
    ("commitElementParams", "commitClipParams"),
    ("formatMissingAssetElementMessage", "formatMissingAssetClipMessage"),
    ("elementHasMissingAsset", "clipHasMissingAsset"),
    ("elementTimelineIssueWithAssets", "clipTimelineIssueWithAssets"),
    ("useElementTimelineIssueWithAssets", "useClipTimelineIssueWithAssets"),
    ("resolveVideoElementLabel", "resolveVideoClipLabel"),
    ("computeVideoElementFit", "computeVideoClipFit"),
    ("ExportedElementParams", "ExportedClipParams"),
    ("buildElementParamsExport", "buildClipParamsExport"),
    ("serializeElementParamsExport", "serializeClipParamsExport"),
    ("InvalidParamsElementRef", "InvalidParamsClipRef"),
    ("ElementTimelineIssue", "ClipTimelineIssue"),
    ("elementTimelineIssue", "clipTimelineIssue"),
    ("formatInvalidParamsElementEventMessage", "formatInvalidParamsClipEventMessage"),
    ("useElementTimelineIssue", "useClipTimelineIssue"),
    ("prefetchProjectNodeDetails", "prefetchProjectClipDetails"),
    ("collectProjectNodeTypes", "collectProjectClipTypes"),
    ("parseElementParamsClipboard", "parseClipParamsClipboard"),
    ("validateElementParamsIdentity", "validateClipParamsIdentity"),
    ("mergeImportedElementParams", "mergeImportedClipParams"),
    ("ImportElementParamsErrorCode", "ImportClipParamsErrorCode"),
    ("ImportElementParamsError", "ImportClipParamsError"),
    ("ImportElementParamsReport", "ImportClipParamsReport"),
]

LINE_SKIP_RE = re.compile(
    r"time_mode\s*=\s*[\"']element[\"']"
    r"|pixfabrica/element-params"
    r"|element-move"
    r"|elementPreviewMode"
    r"|elementId"
    r"|createElement"
    r"|instanceof Element"
    r"|HTMLElement"
    r"|kind:\s*['\"]element['\"]"
    r"|kind\s+in\s+\([\"']clip[\"'],\s*[\"']element[\"']\)"
    r"|field\.element"
    r"|\.option\.element"
    r"|@deprecated"
    r"|export type Element ="
    r"|export function ElementParamsEditor"
    r"|export function ElementEffectsSection"
    r"|resolvedElementDuration"
)

PARAM_RENAMES = [
    (re.compile(r"\belement_index\b"), "clip_index"),
    (re.compile(r"\belement_index,"), "clip_index,"),
    (re.compile(r"element: VisualClip"), "clip: VisualClip"),
    (re.compile(r"element: Clip"), "clip: Clip"),
    (re.compile(r"element: dict\[str, Any\]"), "clip: dict[str, Any]"),
    (re.compile(r"element: Any"), "clip: Any"),
    (re.compile(r"element=element\b"), "clip=clip"),
    (re.compile(r"for element in track\.clips"), "for clip in track.clips"),
    (re.compile(r"for element in elements"), "for clip in clips"),
    (
        re.compile(r"for element_index, element in enumerate\(elements\)"),
        "for clip_index, clip in enumerate(clips)",
    ),
    (re.compile(r"elements = track\.get\(\"clips\"\)"), 'clips = track.get("clips")'),
    (re.compile(r"if not isinstance\(elements, list\)"), "if not isinstance(clips, list)"),
    (re.compile(r"element_index, field\)"), "clip_index, field)"),
    (re.compile(r"track \{track_index\} element \{"), "track {track_index} clip {"),
    (re.compile(r"text elements"), "text clips"),
    (re.compile(r"per element"), "per clip"),
    (re.compile(r"two elements"), "two clips"),
    (re.compile(r"element sub-rows"), "clip sub-rows"),
    (re.compile(r"element panes"), "clip panes"),
    (re.compile(r"element\.get\("), "clip.get("),
    (re.compile(r"\bconst element ="), "const clip ="),
    (re.compile(r"\{element\?"), "{clip?"),
    (re.compile(r"element\?\.effects"), "clip?.effects"),
    (re.compile(r"element\.label"), "clip.label"),
    (re.compile(r"element preview"), "clip preview"),
    (re.compile(r"Each element receives"), "Each clip receives"),
    (re.compile(r"element 0 receives"), "clip 0 receives"),
    (re.compile(r"element 1 receives"), "clip 1 receives"),
    (re.compile(r"two elements only"), "two clips only"),
    (re.compile(r"element string params"), "clip string params"),
    (re.compile(r"single element"), "single clip"),
    (re.compile(r"Per-call audio frame for this element"), "Per-call audio frame for this clip"),
    (re.compile(r"parent visual element"), "parent visual clip"),
    (re.compile(r"GL element on track"), "GL clip on track"),
    (re.compile(r"element\.start absolutized"), "clip.start absolutized"),
    (re.compile(r"Tracks declare elements:"), "Tracks declare clips:"),
    (re.compile(r"each element using"), "each clip using"),
    (re.compile(r"def _element\("), "def _clip("),
]


def should_process(path: Path) -> bool:
    if path.name in SKIP_BASENAMES:
        return False
    rel = path.relative_to(ROOT).as_posix()
    for pattern in SKIP_GLOBS:
        if path.match(pattern) or Path(rel).match(pattern.replace("**/", "")):
            return False
    if path.suffix not in {".py", ".ts", ".tsx"}:
        return False
    # Keep thin shim filenames but still allow content updates in non-shim paths.
    element_shim_names = {
        "elementPreviewClient.ts",
        "elementPreviewPayload.ts",
        "elementPreviewRefresh.ts",
        "elementPreviewAudio.ts",
        "elementPreviewMode.ts",
        "elementBusPreview.ts",
        "elementMove.ts",
        "elementParamsExport.ts",
        "elementParamsImport.ts",
        "invalidElementParams.ts",
        "ElementEffectsSection.tsx",
    }
    return not (
        path.name.startswith("element")
        and path.name.endswith((".ts", ".tsx"))
        and path.name in element_shim_names
    )


def transform_line(line: str) -> str:
    if LINE_SKIP_RE.search(line):
        return line
    for old, new in IDENT_RENAMES:
        if old == new:
            continue
        line = re.sub(rf"\b{re.escape(old)}\b", new, line)
    for pattern, repl in PARAM_RENAMES:
        line = pattern.sub(repl, line)
    return line


def transform_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    out = [transform_line(line) for line in lines]
    new_text = "".join(out)
    if new_text != text:
        path.write_text(new_text, encoding="utf-8")
        return True
    return False


def main() -> None:
    changed: list[str] = []
    for base in (
        "api",
        "core",
        "renderer",
        "web/src",
        "cli",
        "plugins/std/tests",
        "plugins/std_effects/tests",
    ):
        root = ROOT / base
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or not should_process(path):
                continue
            if transform_file(path):
                changed.append(path.relative_to(ROOT).as_posix())
    print(f"updated {len(changed)} files")
    for name in sorted(changed)[:60]:
        print(f"  {name}")
    if len(changed) > 60:
        print(f"  ... and {len(changed) - 60} more")


if __name__ == "__main__":
    main()
