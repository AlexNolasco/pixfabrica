from fastapi.testclient import TestClient

from pixfabrica_api.main import app
from pixfabrica_api.server_config import (
    DEFAULT_MAX_PREVIEW_LONG_SIDE,
    FALLBACK_LOCALE,
    MAX_CLIPS_PER_TRACK,
    MAX_DURATION_S,
    MAX_FPS,
    MAX_HEIGHT,
    MAX_PREVIEW_LONG_SIDE,
    MAX_TRACKS,
    MAX_WIDTH,
    resolve_default_locale,
)
from pixfabrica_core.media_upload import MEDIA_UPLOAD_LIMITS
from pixfabrica_core.preview_dims import DEFAULT_MAX_PREVIEW_LONG_SIDE as CORE_MAX_PREVIEW_LONG_SIDE

client = TestClient(app)
AUTH = {"Authorization": "Bearer pixfabrica-dev-token"}


def test_max_preview_long_side_matches_core_default():
    assert DEFAULT_MAX_PREVIEW_LONG_SIDE is CORE_MAX_PREVIEW_LONG_SIDE


def test_config_returns_policy_limits(monkeypatch):
    monkeypatch.setattr("pixfabrica_api.routes.config.pexels_available", lambda: False)
    response = client.get("/config", headers=AUTH)
    assert response.status_code == 200
    data = response.json()
    assert data["max_preview_long_side"] == MAX_PREVIEW_LONG_SIDE
    assert data["max_duration_s"] == MAX_DURATION_S
    assert data["max_width"] == MAX_WIDTH
    assert data["max_height"] == MAX_HEIGHT
    assert data["max_fps"] == MAX_FPS
    assert data["max_tracks"] == MAX_TRACKS
    assert data["max_clips_per_track"] == MAX_CLIPS_PER_TRACK
    assert data["upload_limits"] == MEDIA_UPLOAD_LIMITS
    assert "capabilities" in data
    assert isinstance(data["capabilities"]["gl_available"], bool)
    assert data["pexels_default_queries"] == []


def test_config_returns_default_locale():
    response = client.get("/config", headers=AUTH)
    assert response.status_code == 200
    assert response.json()["default_locale"] == FALLBACK_LOCALE


def test_config_default_locale_from_env(monkeypatch):
    monkeypatch.setattr("pixfabrica_api.routes.config.DEFAULT_LOCALE", "ja")
    response = client.get("/config", headers=AUTH)
    assert response.status_code == 200
    assert response.json()["default_locale"] == "ja"


def test_resolve_default_locale_accepts_supported_tags():
    assert resolve_default_locale(None) == FALLBACK_LOCALE
    assert resolve_default_locale("") == FALLBACK_LOCALE
    assert resolve_default_locale("ja") == "ja"
    assert resolve_default_locale("zh-CN") == "zh-CN"


def test_resolve_default_locale_clamps_invalid_tags():
    assert resolve_default_locale("fr") == FALLBACK_LOCALE
    assert resolve_default_locale("jp") == FALLBACK_LOCALE


def test_config_includes_pexels_default_queries(monkeypatch):
    monkeypatch.setenv("PIXFABRICA_PEXELS_API_KEY", "test-key")
    monkeypatch.setenv("PIXFABRICA_PEXELS_DEFAULT_QUERIES", "abstract, neon")
    monkeypatch.setenv("PIXFABRICA_PEXELS_DEFAULT_VIDEO_QUERIES", "city, neon")
    response = client.get("/config", headers=AUTH)
    assert response.status_code == 200
    data = response.json()
    assert data["pexels_default_queries"] == ["abstract", "neon"]
    assert data["pexels_default_video_queries"] == ["city", "neon"]
