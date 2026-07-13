from fastapi.testclient import TestClient

from pixfabrica_api.catalog_cache import rebuild_catalog_cache
from pixfabrica_api.main import app

client = TestClient(app)
AUTH = {"Authorization": "Bearer pixfabrica-dev-token"}


def test_catalog_clips_endpoint():
    rebuild_catalog_cache()
    res = client.get("/catalog/clips", params={"lang": "en"}, headers=AUTH)
    assert res.status_code == 200
    clips = res.json()
    assert isinstance(clips, list)
    assert len(clips) > 0
    sample = clips[0]
    assert "clip_type" in sample
    assert "label" in sample
    assert "track_kind" in sample
    kinds = {n["track_kind"] for n in clips}
    assert "skia" in kinds


def test_catalog_clip_detail_sweep_lines_defaults():
    rebuild_catalog_cache()
    res = client.get("/catalog/clips/std-sweep-lines", params={"lang": "en"}, headers=AUTH)
    assert res.status_code == 200
    body = res.json()
    assert body["defaults"]["color"] == "neutral"


def test_catalog_clip_detail_endpoint():
    rebuild_catalog_cache()
    res = client.get("/catalog/clips/std-gradient", params={"lang": "en"}, headers=AUTH)
    assert res.status_code == 200
    body = res.json()
    assert body["clip_type"] == "std-gradient"
    assert body["plugin_id"] == "pixfabrica-std"
    assert isinstance(body["ui"], dict)
    assert "controls" in body["ui"]
    assert isinstance(body["defaults"], dict)
    assert isinstance(body["parameters_schema"], dict)
    assert isinstance(body["labels"], dict)
    assert "fields" in body["labels"]
    assert "opacity" in body["labels"]["fields"]


def test_catalog_clip_detail_unknown():
    rebuild_catalog_cache()
    res = client.get("/catalog/clips/does-not-exist", headers=AUTH)
    assert res.status_code == 404


def test_catalog_clips_track_kind_filter():
    rebuild_catalog_cache()
    res = client.get("/catalog/clips", params={"lang": "en", "track_kind": "post"}, headers=AUTH)
    assert res.status_code == 200
    clips = res.json()
    assert all(n["track_kind"] == "post" for n in clips)


def test_catalog_effects_list_shape():
    rebuild_catalog_cache()
    res = client.get("/catalog/effects", params={"lang": "en"}, headers=AUTH)
    assert res.status_code == 200
    effects = res.json()
    assert isinstance(effects, list)
    assert len(effects) > 0
    sample = effects[0]
    assert sample["effect_type"]
    assert "effect_backend" in sample
