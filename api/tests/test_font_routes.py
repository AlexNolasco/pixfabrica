"""Font catalog API routes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from font_fixtures import write_minimal_font

from pixfabrica_api.main import app

client = TestClient(app)
AUTH = {"Authorization": "Bearer pixfabrica-dev-token"}


@pytest.fixture(autouse=True)
def _fonts_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    fonts_dir = tmp_path / "fonts"
    user_dir = tmp_path / "user-fonts"
    fonts_dir.mkdir()
    user_dir.mkdir()
    write_minimal_font(fonts_dir / "Fixture-Regular.ttf", family_name="Fixture Sans", weight=400)
    manifest = {
        "version": 1,
        "families": [
            {
                "id": "fixture-sans",
                "family": "Fixture Sans",
                "label": "Fixture Sans",
                "category": "sans",
                "weights": [{"value": 400, "source": "Fixture-Regular.ttf"}],
            }
        ],
    }
    (fonts_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    from fontTools.ttLib.woff2 import compress

    compress(str(fonts_dir / "Fixture-Regular.ttf"), str(fonts_dir / "Fixture-Regular.woff2"))

    monkeypatch.setenv("PIXFABRICA_BUNDLED_FONTS_DIR", str(fonts_dir))
    monkeypatch.setenv("PIXFABRICA_USER_FONTS_DIR", str(user_dir))
    monkeypatch.delenv("PIXFABRICA_FONTS_DIR", raising=False)

    from pixfabrica_api.font_jobs import reset_font_jobs_for_tests
    from pixfabrica_core.fonts import rebuild_font_catalog

    reset_font_jobs_for_tests()
    rebuild_font_catalog()
    return fonts_dir


def test_list_fonts() -> None:
    response = client.get("/fonts", headers=AUTH)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == "fixture-sans"
    assert data[0]["weights"][0]["preview_url"] == "/fonts/files/Fixture-Regular.woff2"


def test_get_font_file() -> None:
    response = client.get("/fonts/files/Fixture-Regular.woff2", headers=AUTH)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("font/")


def test_get_font_file_no_auth() -> None:
    """@font-face fetches cannot send Bearer tokens."""
    response = client.get("/fonts/files/Fixture-Regular.woff2")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("font/")


def test_get_font_file_not_found() -> None:
    assert client.get("/fonts/files/missing.woff2", headers=AUTH).status_code == 404


def _wait_for_font_job(job_id: str) -> dict:
    import time

    for _ in range(100):
        response = client.get(f"/fonts/jobs/{job_id}", headers=AUTH)
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] != "pending":
            return payload
        time.sleep(0.02)
    raise AssertionError("font install job did not finish")


def test_upload_font_installs_into_catalog(tmp_path: Path) -> None:
    upload_path = tmp_path / "Custom-Regular.ttf"
    write_minimal_font(upload_path, family_name="Custom Family", weight=400)

    with upload_path.open("rb") as handle:
        response = client.post(
            "/fonts",
            headers=AUTH,
            files={"file": ("Custom-Regular.ttf", handle, "font/ttf")},
        )
    assert response.status_code == 200
    job_id = response.json()["job_id"]

    job = _wait_for_font_job(job_id)
    assert job["status"] == "completed"
    assert job["families"] == ["Custom Family"]

    catalog = client.get("/fonts", headers=AUTH).json()
    assert any(entry["id"] == "custom-family" for entry in catalog)
    assert client.get("/fonts/files/Custom-Regular.woff2", headers=AUTH).status_code == 200
