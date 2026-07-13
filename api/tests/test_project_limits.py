"""Tests for hosted API timeline policy validation."""

from __future__ import annotations

from typing import cast

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from pixfabrica_api.main import app
from pixfabrica_api.project_limits import LimitErrorPayload, validate_graph_policy
from pixfabrica_api.server_config import MAX_CLIPS_PER_TRACK, MAX_TRACKS

client = TestClient(app)
AUTH = {"Authorization": "Bearer pixfabrica-dev-token"}


def _minimal_graph(*, tracks: list | None = None, sounds: list | None = None) -> dict:
    return {
        "title": "Test",
        "description": "Policy test",
        "tracks": tracks if tracks is not None else [],
        "sounds": sounds if sounds is not None else [],
    }


def _track(track_id: str, *, clips: list | None = None) -> dict:
    return {
        "clip_type": "std-skia-track",
        "id": track_id,
        "start": 0,
        "clips": clips if clips is not None else [],
    }


def _clip(clip_id: str) -> dict:
    return {
        "clip_type": "std-gradient",
        "id": clip_id,
        "start": 0,
    }


def test_validate_graph_accepts_within_limits() -> None:
    graph = _minimal_graph(
        tracks=[_track("t1", clips=[_clip("e1")])],
        sounds=[{"sound_type": "std-sound", "id": "s1", "bus": "main", "source": ""}],
    )
    validate_graph_policy(graph)


def test_validate_graph_rejects_too_many_rows() -> None:
    tracks = [_track(f"t{i}") for i in range(MAX_TRACKS)]
    graph = _minimal_graph(
        tracks=tracks, sounds=[{"sound_type": "std-sound", "id": "s1", "bus": "a", "source": ""}]
    )
    with pytest.raises(HTTPException) as exc:
        validate_graph_policy(graph)
    assert exc.value.status_code == 422
    detail = cast(LimitErrorPayload, exc.value.detail)
    assert detail["code"] == "limit_tracks_exceeded"
    assert detail["max"] == MAX_TRACKS
    assert detail["actual"] == MAX_TRACKS + 1


def test_validate_graph_rejects_too_many_clips() -> None:
    clips = [_clip(f"e{i}") for i in range(MAX_CLIPS_PER_TRACK + 1)]
    graph = _minimal_graph(tracks=[_track("t1", clips=clips)])
    with pytest.raises(HTTPException) as exc:
        validate_graph_policy(graph)
    detail = cast(LimitErrorPayload, exc.value.detail)
    assert detail["code"] == "limit_clips_per_track_exceeded"
    assert detail["max"] == MAX_CLIPS_PER_TRACK
    assert detail["actual"] == MAX_CLIPS_PER_TRACK + 1


def test_create_job_rejects_over_limit_graph() -> None:
    tracks = [_track(f"t{i}") for i in range(MAX_TRACKS + 1)]
    graph = _minimal_graph(tracks=tracks)
    res = client.post("/jobs", json={"graph": graph}, headers=AUTH)
    assert res.status_code == 422
    body = res.json()
    assert body["detail"]["code"] == "limit_tracks_exceeded"


def test_validate_graph_rejects_duration_over_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pixfabrica_api.project_limits.MAX_DURATION_S", 60)
    graph = {**_minimal_graph(), "duration": 90.0}
    with pytest.raises(HTTPException) as exc:
        validate_graph_policy(graph)
    detail = cast(LimitErrorPayload, exc.value.detail)
    assert detail["code"] == "limit_duration_exceeded"
    assert detail["max"] == 60


def test_validate_graph_rejects_width_over_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pixfabrica_api.project_limits.MAX_WIDTH", 960)
    graph = {**_minimal_graph(), "width": 1920, "height": 540}
    with pytest.raises(HTTPException) as exc:
        validate_graph_policy(graph)
    detail = cast(LimitErrorPayload, exc.value.detail)
    assert detail["code"] == "limit_width_exceeded"
    assert detail["max"] == 960


def test_validate_graph_allows_duration_at_inclusive_max(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pixfabrica_api.project_limits.MAX_DURATION_S", 600)
    graph = {**_minimal_graph(), "duration": 600.0}
    validate_graph_policy(graph)
