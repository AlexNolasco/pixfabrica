"""Theme preset and extraction API routes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from pixfabrica_api.main import app

client = TestClient(app)
AUTH = {"Authorization": "Bearer pixfabrica-dev-token"}


def test_list_theme_presets() -> None:
    res = client.get("/theme/presets", headers=AUTH)
    assert res.status_code == 200
    presets = res.json()
    assert len(presets) == 16
    first = presets[0]
    assert first["theme"] == "amber"
    assert first["variant"] == "dark"
    assert "primary" in first["colors"]


def test_extract_palette_missing_source() -> None:
    res = client.post("/theme/extract", json={"source": "   "}, headers=AUTH)
    assert res.status_code == 400


def test_extract_palette_missing_file() -> None:
    res = client.post(
        "/theme/extract",
        json={"source": "C:/no/such/palette-image.jpg"},
        headers=AUTH,
    )
    assert res.status_code == 404
