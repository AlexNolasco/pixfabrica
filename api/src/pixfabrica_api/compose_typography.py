"""Typography role guidance for the compose agent."""

from __future__ import annotations

from typing import Any

_HERO_ROLES = frozenset(
    {"display_large", "display_medium", "display_small", "title_large"},
)
_METADATA_ROLES = frozenset({"label_large", "label_medium", "label_small"})


def list_typography_roles_for_compose() -> dict[str, Any]:
    """Compact role catalog for compose tools."""
    return {
        "ok": True,
        "groups": [
            {
                "roles": ["display_large", "display_medium", "display_small"],
                "use": "One hero line per scene; prefer display_large for the main title",
            },
            {
                "roles": ["title_large", "title_medium", "title_small"],
                "use": "Section headers and secondary headings (not tiny metadata)",
            },
            {
                "roles": ["body_large", "body_medium", "body_small"],
                "use": "Readable sentences, lyrics blocks, longer copy",
            },
            {
                "roles": ["label_large", "label_medium", "label_small"],
                "use": "Artist, album, year — pair with offset_y ~0.65 below a hero line",
            },
            {
                "roles": ["mono_large", "mono_medium", "mono_small"],
                "use": "Counters, timestamps, debug — not main titles",
            },
        ],
        "defaults": {
            "hero": "display_large",
            "subtitle": "label_medium",
            "body": "body_medium",
        },
    }


def typography_role_of(clip: Any) -> str | None:
    role = getattr(clip, "typography_role", None)
    if isinstance(role, str) and role:
        return role
    return None


def is_hero_typography_role(role: str | None) -> bool:
    return role in _HERO_ROLES


def is_metadata_typography_role(role: str | None) -> bool:
    return role in _METADATA_ROLES


def lint_typography_roles(text_clips: list[Any], track_id: str) -> tuple[list[str], list[str]]:
    warnings: list[str] = []
    hints: list[str] = []

    hero_clips = [el for el in text_clips if is_hero_typography_role(typography_role_of(el))]
    if len(hero_clips) > 1:
        roles = ", ".join(typography_role_of(el) or "?" for el in hero_clips)
        warnings.append(
            f"track {track_id}: multiple hero typography roles ({roles}) — pick one display/title hero"
        )
        hints.append(
            "Use display_large for the main title; label_medium or title_small for artist/metadata"
        )

    if len(text_clips) >= 2:
        roles = [typography_role_of(el) for el in text_clips]
        if all(
            is_hero_typography_role(role) or role in {"title_medium", "title_small"}
            for role in roles
            if role
        ):
            warnings.append(
                f"track {track_id}: all text uses large roles — hierarchy will look flat"
            )
            hints.append(
                "Pair display_large or title_large (hero) with label_medium for secondary text"
            )

    mono_only = all((typography_role_of(el) or "").startswith("mono_") for el in text_clips)
    if text_clips and mono_only:
        warnings.append(
            f"track {track_id}: text uses only mono_* roles — not suited for main titles"
        )
        hints.append("Use display_large or title_large for the primary line")

    return warnings, hints
