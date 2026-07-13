"""API tests for catalog license filtering and graph validation."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from pixfabrica_api.catalog_cache import rebuild_catalog_cache
from pixfabrica_api.catalog_config import load_excluded_licenses
from pixfabrica_api.license_policy import validate_graph_license_policy
from pixfabrica_api.main import app

client = TestClient(app)
AUTH = {"Authorization": "Bearer pixfabrica-dev-token"}


@pytest.fixture(autouse=True)
def _clear_license_config_cache():
    load_excluded_licenses.cache_clear()
    yield
    load_excluded_licenses.cache_clear()


def test_catalog_clips_include_license(monkeypatch):
    monkeypatch.delenv("PIXFABRICA_CATALOG_EXCLUDED_LICENSES", raising=False)
    rebuild_catalog_cache()
    res = client.get("/catalog/clips", params={"lang": "en"}, headers=AUTH)
    assert res.status_code == 200
    star_dust = next(n for n in res.json() if n["clip_type"] == "std-star-dust-gl")
    assert star_dust["license"] == "CC-BY-NC-SA-3.0"
    assert star_dust["disabled"] is False


def test_catalog_clips_mark_nc_disabled_when_excluded(monkeypatch):
    monkeypatch.setenv(
        "PIXFABRICA_CATALOG_EXCLUDED_LICENSES",
        "CC-BY-NC-SA-3.0,CC-BY-NC-SA-4.0",
    )
    load_excluded_licenses.cache_clear()
    rebuild_catalog_cache()
    res = client.get("/catalog/clips", params={"lang": "en"}, headers=AUTH)
    assert res.status_code == 200
    star_dust = next(n for n in res.json() if n["clip_type"] == "std-star-dust-gl")
    assert star_dust["disabled"] is True
    assert star_dust["restricted_reason"] == "license"


def test_config_exposes_catalog_policy(monkeypatch):
    monkeypatch.setenv("PIXFABRICA_CATALOG_EXCLUDED_LICENSES", "CC-BY-NC-SA-3.0")
    load_excluded_licenses.cache_clear()
    res = client.get("/config", headers=AUTH)
    assert res.status_code == 200
    assert res.json()["catalog"]["excluded_licenses"] == ["CC-BY-NC-SA-3.0"]


def test_validate_graph_license_policy_blocks_excluded_node(monkeypatch):
    monkeypatch.setenv("PIXFABRICA_CATALOG_EXCLUDED_LICENSES", "CC-BY-NC-SA-3.0")
    load_excluded_licenses.cache_clear()
    rebuild_catalog_cache()
    graph = {
        "title": "t",
        "description": "d",
        "width": 640,
        "height": 480,
        "fps": 30,
        "duration": 1,
        "locale": "en",
        "tracks": [
            {
                "id": "trk1",
                "label": "GL",
                "track_kind": "gl",
                "enabled": True,
                "clips": [
                    {
                        "id": "el1",
                        "clip_type": "std-star-dust-gl",
                        "enabled": True,
                        "start": 0,
                        "duration": 1,
                    }
                ],
            }
        ],
        "sounds": [],
    }
    with pytest.raises(HTTPException) as exc:
        validate_graph_license_policy(graph)
    assert exc.value.status_code == 422
