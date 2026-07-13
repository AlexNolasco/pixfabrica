"""Tests for OpenGL capability policy enforcement."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pixfabrica_api.catalog_cache import rebuild_catalog_cache
from pixfabrica_api.main import app
from pixfabrica_api.plugin_registry import ensure_plugins_registered
from pixfabrica_core.capabilities.gl import GL_UNAVAILABLE_CODE

AUTH = {"Authorization": "Bearer pixfabrica-dev-token"}

HELLO_GRAPH: dict = {
    "title": "Hello",
    "description": "",
    "width": 1280,
    "height": 720,
    "fps": 24.0,
    "duration": 5.0,
    "tracks": [
        {
            "clip_type": "std-skia-track",
            "id": "track-1",
            "clips": [
                {
                    "clip_type": "std-solid-background",
                    "id": "bg-1",
                    "color": "background",
                }
            ],
        }
    ],
}

GL_GRAPH: dict = {
    **HELLO_GRAPH,
    "tracks": [
        {
            "clip_type": "std-gl-track",
            "id": "track-1",
            "clips": [],
        }
    ],
}


@pytest.fixture
def client() -> TestClient:
    rebuild_catalog_cache()
    ensure_plugins_registered()
    return TestClient(app)


def test_create_job_allows_skia_when_gl_unavailable(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("pixfabrica_api.gl_policy.gl_available", lambda: False)
    monkeypatch.setattr(
        "pixfabrica_api.routes.jobs.job_service.create_job",
        lambda graph: "fake-job-id",
    )
    response = client.post("/jobs", json={"graph": HELLO_GRAPH}, headers=AUTH)
    assert response.status_code == 200


def test_create_job_rejects_gl_graph_when_unavailable(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("pixfabrica_api.gl_policy.gl_available", lambda: False)
    response = client.post("/jobs", json={"graph": GL_GRAPH}, headers=AUTH)
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == GL_UNAVAILABLE_CODE


def test_catalog_marks_gl_clips_disabled_when_unavailable(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("pixfabrica_api.routes.catalog.gl_available", lambda: False)
    response = client.get("/catalog/clips", headers=AUTH)
    assert response.status_code == 200
    rows = response.json()
    gl_rows = [row for row in rows if row["track_kind"] == "gl"]
    assert gl_rows
    assert all(row["disabled"] for row in gl_rows)


def test_validate_graph_for_compose_reports_gl_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pixfabrica_api.compose_graph import validate_graph_for_compose

    rebuild_catalog_cache()
    ensure_plugins_registered()
    monkeypatch.setattr("pixfabrica_api.gl_policy.gl_available", lambda: False)
    result = validate_graph_for_compose(GL_GRAPH)
    assert result["ok"] is False
    assert result["code"] == GL_UNAVAILABLE_CODE
