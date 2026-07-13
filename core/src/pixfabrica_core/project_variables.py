"""Resolve {TITLE} / {AUTHOR} tokens in clip string params once at job load."""

from __future__ import annotations

import re
from typing import Any, get_args, get_origin

from pydantic.fields import FieldInfo

from pixfabrica_core.clips import Clip, RenderJob, VisualClip
from pixfabrica_core.prepare_diagnostics import PrepareDiagnostics, PrepareWarning

TOKEN_PATTERN = re.compile(r"\{([A-Z][A-Z0-9_]*)\}")
KNOWN_TOKENS = frozenset({"TITLE", "AUTHOR"})


def project_variable_mapping(*, title: str, author: str) -> dict[str, str]:
    return {
        "TITLE": title,
        "AUTHOR": author,
    }


def _is_string_annotation(annotation: Any) -> bool:
    if annotation is str:
        return True
    origin = get_origin(annotation)
    if origin is None:
        return False
    args = get_args(annotation)
    return str in args


def _field_widget(field_info: FieldInfo) -> str | None:
    extra = field_info.json_schema_extra
    if isinstance(extra, dict):
        widget = extra.get("widget")
        if isinstance(widget, str):
            return widget
    return None


def _substitutable_field_names(type_cls: type[Clip]) -> frozenset[str]:
    names: set[str] = set()
    for name, field_info in type_cls.model_fields.items():
        if name == "source":
            continue
        if _field_widget(field_info) == "file":
            continue
        if not _is_string_annotation(field_info.annotation):
            continue
        names.add(name)
    return frozenset(names)


def _clip_schema_class(clip: Clip) -> type[Clip] | None:
    from pixfabrica_core.composition.effect_registry import _EFFECT_REGISTRY
    from pixfabrica_core.composition.registry import _CLIP_TYPE_REGISTRY
    from pixfabrica_core.composition.unknown import UnknownClip, UnknownEffect

    if isinstance(clip, (UnknownClip, UnknownEffect)):
        return None
    clip_type = getattr(clip, "clip_type", "")
    if clip_type in _CLIP_TYPE_REGISTRY:
        return _CLIP_TYPE_REGISTRY[clip_type]
    if clip_type in _EFFECT_REGISTRY:
        return _EFFECT_REGISTRY[clip_type]
    return type(clip)


def substitute_project_variables(
    value: str,
    mapping: dict[str, str],
) -> tuple[str, list[str]]:
    """Return substituted text and unknown token names (uppercase)."""
    if "{" not in value:
        return value, []

    unknown: list[str] = []

    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        if key in mapping:
            return mapping[key]
        if key not in KNOWN_TOKENS:
            unknown.append(key)
        return match.group(0)

    return TOKEN_PATTERN.sub(repl, value), unknown


def _apply_to_clip(
    clip: Clip,
    mapping: dict[str, str],
) -> list[PrepareWarning]:
    type_cls = _clip_schema_class(clip)
    if type_cls is None:
        return []

    warnings: list[PrepareWarning] = []
    for field_name in _substitutable_field_names(type_cls):
        raw = getattr(clip, field_name, None)
        if not isinstance(raw, str) or "{" not in raw:
            continue
        resolved, unknown = substitute_project_variables(raw, mapping)
        if resolved != raw:
            setattr(clip, field_name, resolved)
        for token in unknown:
            warnings.append(
                PrepareWarning(
                    kind="clip",
                    ref_id=clip.id,
                    clip_type=getattr(clip, "clip_type", ""),
                    field=field_name,
                    source=token,
                    code="unknown_project_variable",
                    message=f"Unknown project variable {{{token}}}",
                )
            )
    return warnings


def apply_project_variables_to_clip(
    clip: Clip,
    *,
    title: str,
    author: str,
) -> list[PrepareWarning]:
    """Resolve tokens on a single clip (isolated clip preview path)."""
    mapping = project_variable_mapping(title=title, author=author)
    warnings = _apply_to_clip(clip, mapping)
    if isinstance(clip, VisualClip):
        for effect in clip.effects:
            warnings.extend(_apply_to_clip(effect, mapping))
    return warnings


def apply_project_variables(job: RenderJob) -> list[PrepareWarning]:
    """Resolve tokens on all track clips (and nested effects) in place."""
    mapping = project_variable_mapping(title=job.title, author=job.author)
    warnings: list[PrepareWarning] = []
    for track in job.tracks:
        for clip in track.clips:
            warnings.extend(_apply_to_clip(clip, mapping))
            if isinstance(clip, VisualClip):
                for effect in clip.effects:
                    warnings.extend(_apply_to_clip(effect, mapping))
        for effect in track.effects:
            warnings.extend(_apply_to_clip(effect, mapping))
    return warnings


def merge_project_variable_warnings(job: RenderJob, diagnostics: PrepareDiagnostics) -> None:
    """Copy job-load variable warnings into prepare diagnostics."""
    diagnostics.ingest(job.project_variable_warnings())
