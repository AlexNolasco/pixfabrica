"""Tests for project variable substitution at RenderJob load."""

from __future__ import annotations

from pathlib import Path

import pytest

from pixfabrica_core.clips import RenderJob
from pixfabrica_core.composition.effect_registry import register_effect
from pixfabrica_core.composition.registry import register_clip_type
from pixfabrica_core.plugins.discovery import discover_plugins
from pixfabrica_core.project_variables import (
    apply_project_variables_to_clip,
    substitute_project_variables,
)
from pixfabrica_std.player.track_card import TrackCard


@pytest.fixture(autouse=True)
def _register_std_nodes() -> None:
    repo_plugins = Path(__file__).resolve().parents[2] / "plugins"
    discovered, _ = discover_plugins(repo_plugins)
    for plugin in discovered:
        for clip_cls in plugin.clip_types:
            register_clip_type(clip_cls)
        for effect_cls in plugin.effects:
            register_effect(effect_cls)


def test_substitute_known_tokens() -> None:
    text, unknown = substitute_project_variables(
        "By {AUTHOR} — {TITLE}",
        {"TITLE": "Neon Dreams", "AUTHOR": "Alex"},
    )
    assert text == "By Alex — Neon Dreams"
    assert unknown == []


def test_unknown_token_left_literal_with_warning_name() -> None:
    text, unknown = substitute_project_variables(
        "{ALBUM} on {TITLE}",
        {"TITLE": "Hit", "AUTHOR": ""},
    )
    assert text == "{ALBUM} on Hit"
    assert unknown == ["ALBUM"]


def test_render_job_resolves_track_card_params() -> None:
    job = RenderJob.model_validate(
        {
            "title": "My Song",
            "author": "Jane Doe",
            "description": "",
            "width": 1080,
            "height": 1920,
            "fps": 30,
            "duration": 10,
            "tracks": [
                {
                    "clip_type": "std-skia-track",
                    "id": "t1",
                    "clips": [
                        {
                            "clip_type": "std-track-card",
                            "id": "el1",
                            "title": "{TITLE}",
                            "author": "{AUTHOR}",
                            "source": "{TITLE}/cover.png",
                        }
                    ],
                }
            ],
        }
    )
    card = job.tracks[0].clips[0]
    assert isinstance(card, TrackCard)
    assert card.title == "My Song"
    assert card.author == "Jane Doe"
    assert card.source == "{TITLE}/cover.png"


def test_apply_to_single_clip() -> None:
    clip = TrackCard(
        id="el1",
        title="{TITLE}",
        author="feat. {AUTHOR}",
        source="media/cover.jpg",
    )
    warnings = apply_project_variables_to_clip(clip, title="Track", author="Artist")
    assert clip.title == "Track"
    assert clip.author == "feat. Artist"
    assert clip.source == "media/cover.jpg"
    assert warnings == []


def test_unknown_token_emits_prepare_warning() -> None:
    job = RenderJob.model_validate(
        {
            "title": "Song",
            "author": "",
            "description": "",
            "width": 1080,
            "height": 1920,
            "fps": 30,
            "duration": 10,
            "tracks": [
                {
                    "clip_type": "std-skia-track",
                    "id": "t1",
                    "clips": [
                        {
                            "clip_type": "std-track-card",
                            "id": "el1",
                            "title": "{ALBUM}",
                        }
                    ],
                }
            ],
        }
    )
    card = job.tracks[0].clips[0]
    assert isinstance(card, TrackCard)
    assert card.title == "{ALBUM}"
    warnings = job.project_variable_warnings()
    assert len(warnings) == 1
    assert warnings[0].code == "unknown_project_variable"
    assert warnings[0].source == "ALBUM"
