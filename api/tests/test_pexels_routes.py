"""Tests for Pexels stock photo routes."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pixfabrica_api.catalog_cache import rebuild_catalog_cache
from pixfabrica_api.main import app

AUTH = {"Authorization": "Bearer pixfabrica-dev-token"}


@pytest.fixture
def pexels_client(tmp_path, monkeypatch):
    monkeypatch.setenv("PIXFABRICA_MEDIA_ROOT", str(tmp_path))
    monkeypatch.setenv("PUBLIC_API_URL", "http://testserver")
    monkeypatch.setenv("PIXFABRICA_PEXELS_API_KEY", "test-pexels-key")
    rebuild_catalog_cache()
    return TestClient(app)


def test_search_requires_api_key(monkeypatch):
    monkeypatch.delenv("PIXFABRICA_PEXELS_API_KEY", raising=False)
    client = TestClient(app)
    response = client.get(
        "/pexels/search?query=nature&orientation=landscape",
        headers=AUTH,
    )
    assert response.status_code == 503


def test_search_returns_photos(pexels_client, monkeypatch):
    async def _fake_search(**kwargs):
        assert kwargs["query"] == "inspirational"
        assert kwargs["orientation"] == "portrait"
        assert kwargs["size"] == "medium"
        return {
            "page": 1,
            "per_page": 15,
            "total_results": 1,
            "next_page": None,
            "photos": [
                {
                    "id": 42,
                    "width": 800,
                    "height": 1200,
                    "alt": "Test photo",
                    "photographer": "Jane Doe",
                    "photographer_url": "https://www.pexels.com/@jane",
                    "url": "https://www.pexels.com/photo/42/",
                    "src": {
                        "medium": "https://images.pexels.com/photos/42/medium.jpg",
                        "portrait": "https://images.pexels.com/photos/42/portrait.jpg",
                        "original": "https://images.pexels.com/photos/42/original.jpg",
                    },
                }
            ],
        }

    monkeypatch.setattr("pixfabrica_api.routes.pexels.search_pexels_photos", _fake_search)
    response = pexels_client.get(
        "/pexels/search?query=inspirational&orientation=portrait&page=1&per_page=15",
        headers=AUTH,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_results"] == 1
    assert len(data["photos"]) == 1
    assert data["photos"][0]["photographer"] == "Jane Doe"


def test_apply_ingests_photo(pexels_client, monkeypatch, tmp_path):

    fake_image = tmp_path / "ingest-test.jpg"
    fake_image.write_bytes(b"fake-jpeg")

    def _fake_ingest(src, *, orientation, media_root):
        assert orientation == "portrait"
        return fake_image

    async def _fake_optimize(dest, **kwargs):
        from pixfabrica_api.routes.media import OptimizedForResponse

        return OptimizedForResponse(width=1080, height=1920, fps=0.0)

    monkeypatch.setattr("pixfabrica_api.routes.pexels.ingest_pexels_photo", _fake_ingest)
    monkeypatch.setattr("pixfabrica_api.routes.pexels._apply_image_upload_policy", _fake_optimize)

    response = pexels_client.post(
        "/pexels/apply",
        headers=AUTH,
        json={
            "src": {
                "portrait": "https://images.pexels.com/photos/42/portrait.jpg",
                "original": "https://images.pexels.com/photos/42/original.jpg",
            },
            "orientation": "portrait",
            "target_width": 1080,
            "target_height": 1920,
            "provenance": {
                "provider": "pexels",
                "page_url": "https://www.pexels.com/photo/42/",
                "creator_name": "Jane Doe",
                "media_kind": "photo",
            },
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["filename"] == "ingest-test.jpg"
    assert data["path"]
    assert data["source_provider"] == "pexels"
    assert "Jane Doe" in data["source_attribution"]
    assert "https://www.pexels.com/photo/42/" in data["source_attribution"]


def test_apply_photo_with_custom_upload_context(pexels_client, monkeypatch, tmp_path):
    fake_image = tmp_path / "wall.jpg"
    fake_image.write_bytes(b"fake-jpeg")
    captured: dict[str, str] = {}

    def _fake_ingest(src, *, orientation, media_root):
        return fake_image

    async def _fake_optimize(dest, **kwargs):
        captured["clip_type"] = kwargs["clip_type"]
        captured["plugin_id"] = kwargs["plugin_id"]
        captured["field"] = kwargs["field"]
        from pixfabrica_api.routes.media import OptimizedForResponse

        return OptimizedForResponse(width=640, height=480, fps=0.0)

    monkeypatch.setattr("pixfabrica_api.routes.pexels.ingest_pexels_photo", _fake_ingest)
    monkeypatch.setattr("pixfabrica_api.routes.pexels._apply_image_upload_policy", _fake_optimize)

    response = pexels_client.post(
        "/pexels/apply",
        headers=AUTH,
        json={
            "src": {"original": "https://images.pexels.com/photos/1/original.jpg"},
            "orientation": "landscape",
            "target_width": 640,
            "target_height": 480,
            "clip_type": "std-music-room-gl",
            "plugin_id": "pixfabrica-std",
            "field": "wall_source",
        },
    )
    assert response.status_code == 200
    assert captured == {
        "clip_type": "std-music-room-gl",
        "plugin_id": "pixfabrica-std",
        "field": "wall_source",
    }


def test_orientation_helper(pexels_client):
    response = pexels_client.get(
        "/pexels/orientation?width=1080&height=1920",
        headers=AUTH,
    )
    assert response.status_code == 200
    assert response.json() == {"orientation": "portrait"}


def test_video_search_returns_videos(pexels_client, monkeypatch):
    async def _fake_search(**kwargs):
        assert kwargs["query"] == "cinematic"
        assert kwargs["orientation"] == "landscape"
        return {
            "page": 1,
            "per_page": 15,
            "total_results": 1,
            "next_page": None,
            "videos": [
                {
                    "id": 99,
                    "width": 1920,
                    "height": 1080,
                    "duration": 12,
                    "url": "https://www.pexels.com/video/99/",
                    "image": "https://images.pexels.com/videos/99/preview.jpg",
                    "user": {
                        "id": 1,
                        "name": "Alex",
                        "url": "https://www.pexels.com/@alex",
                    },
                    "video_files": [
                        {
                            "id": 1,
                            "quality": "hd",
                            "file_type": "video/mp4",
                            "width": 1280,
                            "height": 720,
                            "fps": 24.0,
                            "size": 5000,
                            "link": "https://player.vimeo.com/external/99.hd.mp4",
                        }
                    ],
                }
            ],
        }

    monkeypatch.setattr("pixfabrica_api.routes.pexels.search_pexels_videos", _fake_search)
    response = pexels_client.get(
        "/pexels/videos/search?query=cinematic&orientation=landscape&page=1&per_page=15",
        headers=AUTH,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_results"] == 1
    assert len(data["videos"]) == 1
    assert data["videos"][0]["user"]["name"] == "Alex"


def test_video_apply_ingests_and_optimizes(pexels_client, monkeypatch, tmp_path):
    fake_video = tmp_path / "ingest-test.mp4"
    fake_video.write_bytes(b"fake-mp4")
    optimized = tmp_path / "ingest-test.proxy.mp4"
    optimized.write_bytes(b"optimized-mp4")

    def _fake_ingest(video_files, *, target_width, target_height, media_root):
        assert target_width == 1920
        assert target_height == 1080
        return fake_video

    async def _fake_optimize(dest, **kwargs):
        from pixfabrica_api.video_transcode import OptimizedFor, VideoOptimizeResult

        assert kwargs["target_fps"] == 30.0
        return VideoOptimizeResult(
            path=optimized,
            optimized_for=OptimizedFor(width=1920, height=1080, fps=30.0),
            transcoded=True,
        )

    monkeypatch.setattr("pixfabrica_api.routes.pexels.ingest_pexels_video", _fake_ingest)
    monkeypatch.setattr("pixfabrica_api.routes.pexels._optimize_video_upload", _fake_optimize)

    response = pexels_client.post(
        "/pexels/videos/apply",
        headers=AUTH,
        json={
            "video_files": [
                {
                    "width": 1280,
                    "height": 720,
                    "link": "https://player.vimeo.com/external/99.hd.mp4",
                }
            ],
            "target_width": 1920,
            "target_height": 1080,
            "target_fps": 30,
            "provenance": {
                "provider": "pexels",
                "page_url": "https://www.pexels.com/video/99/",
                "creator_name": "Alex",
                "media_kind": "video",
            },
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["filename"] == optimized.name
    assert data["optimized_for"]["width"] == 1920
    assert data["source_provider"] == "pexels"
    assert "Alex" in data["source_attribution"]
    assert "https://www.pexels.com/video/99/" in data["source_attribution"]
