"""Tests for render_job() error paths and _check_unknown_clips."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pixfabrica_core.clips import RenderJob
from pixfabrica_core.composition.unknown import UnknownClip, UnknownProjectSetting
from pixfabrica_core.errors import RenderError, RenderErrorCode
from pixfabrica_renderer.render import _check_unknown_clips

_REPO_ROOT = Path(__file__).parent.parent.parent


@pytest.fixture(scope="session", autouse=False)
def std_registry():
    """Populate the clip registry with the std plugin for example-file tests."""
    from pixfabrica_core.composition.registry import register_clip_type, register_setting_type
    from pixfabrica_core.plugins.discovery import discover_plugins

    discovered, _ = discover_plugins(_REPO_ROOT / "plugins")
    for plugin in discovered:
        for clip_cls in plugin.clip_types:
            register_clip_type(clip_cls)
        for cfg_cls in plugin.project_settings:
            register_setting_type(cfg_cls)


# ── Helpers ───────────────────────────────────────────────────────────────────

_VALID_JOB_DATA = {
    "title": "Test",
    "description": "renderer unit test",
    "tracks": [],
}


def _job(**overrides) -> RenderJob:
    return RenderJob.model_validate({**_VALID_JOB_DATA, **overrides})


# ── _check_unknown_clips ──────────────────────────────────────────────────────


def test_clean_job_passes():
    _check_unknown_clips(_job())


def test_unknown_visual_clip_raises():
    unknown = UnknownClip(id="e1", raw_clip_type="acme-rain", raw_data={})
    # Inject via a plain SkiaTrack-like dict so deserialization creates the track
    # but the clip is already an UnknownClip object.
    job = _job()
    object.__setattr__(job, "tracks", [])  # keep empty

    # Build a job whose track has an UnknownClip directly
    from pixfabrica_core.composition.track import SkiaTrack

    track = SkiaTrack(id="t1", start=0.0, duration=10.0, clips=[unknown])
    job2 = _job()
    # Bypass Pydantic immutability to inject the track
    object.__setattr__(job2, "tracks", [track])

    with pytest.raises(RenderError) as exc_info:
        _check_unknown_clips(job2)
    assert exc_info.value.code == RenderErrorCode.UNKNOWN_PLUGIN
    assert exc_info.value.context["clip_type"] == "acme-rain"


def test_unknown_theme_setting_raises():
    unknown_theme = UnknownProjectSetting(id="cfg1", raw_setting_type="acme-theme", raw_data={})
    job = _job()
    object.__setattr__(job, "theme", unknown_theme)
    with pytest.raises(RenderError) as exc_info:
        _check_unknown_clips(job)
    assert exc_info.value.code == RenderErrorCode.UNKNOWN_PLUGIN
    assert exc_info.value.context["clip_type"] == "acme-theme"


def test_unknown_typography_setting_raises():
    unknown_typo = UnknownProjectSetting(id="cfg2", raw_setting_type="acme-typo", raw_data={})
    job = _job()
    object.__setattr__(job, "typography_setting", unknown_typo)
    with pytest.raises(RenderError) as exc_info:
        _check_unknown_clips(job)
    assert exc_info.value.code == RenderErrorCode.UNKNOWN_PLUGIN
    assert exc_info.value.context["clip_type"] == "acme-typo"


# ── Example fixture files ────────────────────────────────────────────────────

_EXAMPLES = Path(__file__).parent.parent.parent / "cli" / "examples"


# ── Fixture JSON round-trip ───────────────────────────────────────────────────


def test_minimal_fixture_json_loads_and_passes_validation(tmp_path):
    """A minimal well-formed JSON job loads cleanly and passes _check_unknown_clips."""
    from pixfabrica_core.load_render_job import load_render_job

    fixture = tmp_path / "minimal.json"
    fixture.write_text(json.dumps(_VALID_JOB_DATA), encoding="utf-8")

    job = load_render_job(fixture)
    assert job.title == "Test"
    _check_unknown_clips(job)  # must not raise


def test_unknown_clip_in_fixture_json_detected(tmp_path):
    """A job JSON containing an unregistered clip type is detected after load."""
    from pixfabrica_core.load_render_job import load_render_job

    data = {
        **_VALID_JOB_DATA,
        "tracks": [
            {
                "clip_type": "std-skia-track",
                "id": "t1",
                "start": 0.0,
                "clips": [{"clip_type": "nonexistent-42", "id": "e1", "start": 0.0}],
            }
        ],
    }
    fixture = tmp_path / "unknown.json"
    fixture.write_text(json.dumps(data), encoding="utf-8")

    job = load_render_job(fixture)
    with pytest.raises(RenderError) as exc_info:
        _check_unknown_clips(job)
    assert exc_info.value.code == RenderErrorCode.UNKNOWN_PLUGIN
    assert "nonexistent-42" in exc_info.value.context["clip_type"]


# ── Example: hello_world.json ─────────────────────────────────────────────────


@pytest.mark.usefixtures("std_registry")
def test_hello_world_example_loads():
    from pixfabrica_core.composition.track import SkiaTrack
    from pixfabrica_core.load_render_job import load_render_job

    job = load_render_job(_EXAMPLES / "hello_world.json")

    _check_unknown_clips(job)
    assert job.width == 1280
    assert job.height == 720
    assert job.fps == 24.0
    assert job.duration == 5.0
    assert len(job.tracks) == 1

    track = job.tracks[0]
    assert isinstance(track, SkiaTrack)
    assert track.transition_in is None
    assert track.transition_out is None

    clip_types = [e.clip_type for e in track.clips]
    assert clip_types == ["std-solid-background", "std-static-text"]


# ── Example: hello_world_transitions.json ─────────────────────────────────────


@pytest.mark.usefixtures("std_registry")
def test_hello_world_transitions_example_loads():
    from pixfabrica_core.composition.track import SkiaTrack, TransitionType
    from pixfabrica_core.load_render_job import load_render_job

    job = load_render_job(_EXAMPLES / "hello_world_transitions.json")

    _check_unknown_clips(job)
    assert job.duration == 6.0
    assert len(job.tracks) == 2

    hello_track, world_track = job.tracks

    # Track types survive deserialization
    assert isinstance(hello_track, SkiaTrack)
    assert isinstance(world_track, SkiaTrack)

    # "Hello" track: no intro, fade outro
    assert hello_track.transition_in is None
    assert hello_track.transition_out is not None
    assert hello_track.transition_out.type == TransitionType.FADE
    assert hello_track.transition_out.duration == 1.5

    # "World" track: fade intro, no outro
    assert world_track.transition_in is not None
    assert world_track.transition_in.type == TransitionType.FADE
    assert world_track.transition_in.duration == 1.5
    assert world_track.transition_out is None
    assert hello_track.duration is not None
    assert world_track.transition_in.duration is not None
    # Overlap: hello ends at 4.5, world starts at 3.0 → 1.5s overlap
    assert (
        hello_track.start + hello_track.duration
        == world_track.start + world_track.transition_in.duration
    )  # type: ignore[operator]

    # Text content
    assert any(getattr(e, "text", None) == "Hello" for e in hello_track.clips)
    assert any(getattr(e, "text", None) == "World" for e in world_track.clips)
