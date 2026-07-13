"""Tests for media upload routes."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pixfabrica_api.audio_transcode import AudioOptimizedFor, AudioOptimizeResult
from pixfabrica_api.catalog_cache import rebuild_catalog_cache
from pixfabrica_api.main import app
from pixfabrica_api.video_transcode import OptimizedFor, VideoOptimizeResult
from pixfabrica_core.media_upload import MEDIA_UPLOAD_LIMITS
from pixfabrica_core.upload_manifest import UPLOAD_MANIFEST_SUFFIX

AUTH = {"Authorization": "Bearer pixfabrica-dev-token"}


@pytest.fixture
def media_client(tmp_path, monkeypatch):
    monkeypatch.setenv("PIXFABRICA_MEDIA_ROOT", str(tmp_path))
    monkeypatch.setenv("PUBLIC_API_URL", "http://testserver")
    return TestClient(app)


@pytest.fixture(autouse=True)
def stub_media_optimize(monkeypatch):
    def _fake_video(source: Path, **kwargs):
        return VideoOptimizeResult(
            path=source,
            optimized_for=OptimizedFor(width=640, height=360, fps=24.0),
            transcoded=False,
        )

    def _fake_audio(source: Path):
        output = source.with_suffix(".m4a")
        output.write_bytes(b"transcoded-aac")
        if source.exists():
            source.unlink()
        return AudioOptimizeResult(
            path=output,
            optimized_for=AudioOptimizedFor(format="aac", bitrate_kbps=192),
            transcoded=True,
        )

    monkeypatch.setattr("pixfabrica_api.routes.media.video_ffmpeg_available", lambda: True)
    monkeypatch.setattr("pixfabrica_api.routes.media.audio_ffmpeg_available", lambda: True)
    monkeypatch.setattr("pixfabrica_api.routes.media.optimize_video_upload", _fake_video)
    monkeypatch.setattr("pixfabrica_api.routes.media.optimize_audio_upload", _fake_audio)


def test_upload_and_fetch(media_client: TestClient, tmp_path):
    data = b"hello audio"
    res = media_client.post(
        "/media?kind=audio",
        headers=AUTH,
        files={"file": ("song.wav", io.BytesIO(data), "audio/wav")},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["filename"] == "song.m4a"
    assert body["size"] == len(b"transcoded-aac")
    assert body["path"] == str((tmp_path / "song.m4a").resolve())
    assert body["url"] == "http://testserver/media/song.m4a"
    assert not (tmp_path / "song.wav").exists()

    get_res = media_client.get("/media/song.m4a", headers=AUTH)
    assert get_res.status_code == 200
    assert get_res.content == b"transcoded-aac"


def test_upload_compressed_audio_passes_through(media_client: TestClient, tmp_path):
    data = b"mp3 bytes"
    res = media_client.post(
        "/media?kind=audio",
        headers=AUTH,
        files={"file": ("song.mp3", io.BytesIO(data), "audio/mpeg")},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["filename"] == "song.mp3"
    assert (tmp_path / "song.mp3").read_bytes() == data


def test_upload_lossless_rejects_over_lossless_limit(media_client: TestClient):
    huge = b"x" * (MEDIA_UPLOAD_LIMITS["audio_lossless"] + 1)
    res = media_client.post(
        "/media?kind=audio",
        headers=AUTH,
        files={"file": ("big.wav", io.BytesIO(huge), "audio/wav")},
    )
    assert res.status_code == 413


def test_upload_compressed_audio_rejects_over_compressed_limit(media_client: TestClient):
    huge = b"x" * (MEDIA_UPLOAD_LIMITS["audio"] + 1)
    res = media_client.post(
        "/media?kind=audio",
        headers=AUTH,
        files={"file": ("big.mp3", io.BytesIO(huge), "audio/mpeg")},
    )
    assert res.status_code == 413


def test_upload_lossless_audio_rejects_without_ffmpeg(
    media_client: TestClient,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr("pixfabrica_api.routes.media.audio_ffmpeg_available", lambda: False)
    res = media_client.post(
        "/media?kind=audio",
        headers=AUTH,
        files={"file": ("song.wav", io.BytesIO(b"wav"), "audio/wav")},
    )
    assert res.status_code == 503
    assert not (tmp_path / "song.wav").exists()
    assert not (tmp_path / "song.m4a").exists()


def test_upload_overwrites(media_client: TestClient, tmp_path):
    media_client.post(
        "/media?kind=default",
        headers=AUTH,
        files={"file": ("clip.wav", io.BytesIO(b"a"), "audio/wav")},
    )
    res = media_client.post(
        "/media?kind=default",
        headers=AUTH,
        files={"file": ("clip.wav", io.BytesIO(b"bbb"), "audio/wav")},
    )
    assert res.status_code == 200
    assert (tmp_path / "clip.wav").read_bytes() == b"bbb"


def test_upload_with_clip_type_query_writes_manifest(media_client: TestClient, tmp_path):
    rebuild_catalog_cache()
    data = b"fake video"
    res = media_client.post(
        "/media?kind=video&clip_type=std-video&plugin_id=pixfabrica-std&target_width=640&target_height=360&target_fps=24",
        headers=AUTH,
        files={"file": ("clip.mp4", io.BytesIO(data), "video/mp4")},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["optimized_for"] == {"width": 640, "height": 360, "fps": 24.0}
    manifest = tmp_path / f"clip.mp4{UPLOAD_MANIFEST_SUFFIX}"
    assert manifest.is_file()
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["clip_type"] == "std-video"
    assert payload["plugin_id"] == "pixfabrica-std"
    assert payload["kind"] == "video"
    assert payload["size"] == len(data)
    assert len(payload["content_sha256"]) == 64
    assert payload["optimized_for"] == {"width": 640, "height": 360, "fps": 24.0}


def test_upload_manifest_endpoint(media_client: TestClient, tmp_path):
    rebuild_catalog_cache()
    data = b"fake video"
    media_client.post(
        "/media?kind=video&clip_type=std-video&plugin_id=pixfabrica-std",
        headers=AUTH,
        files={"file": ("clip.mp4", io.BytesIO(data), "video/mp4")},
    )
    res = media_client.get("/media/clip.mp4/upload-manifest", headers=AUTH)
    assert res.status_code == 200
    assert res.json()["optimized_for"] == {"width": 640, "height": 360, "fps": 24.0}


def test_upload_rejects_partial_clip_context(media_client: TestClient):
    rebuild_catalog_cache()
    res = media_client.post(
        "/media?kind=video&clip_type=std-video",
        headers=AUTH,
        files={"file": ("clip.mp4", io.BytesIO(b"x"), "video/mp4")},
    )
    assert res.status_code == 400
    assert "together" in res.json()["detail"]


def test_upload_rejects_unknown_clip_plugin_pair(media_client: TestClient):
    rebuild_catalog_cache()
    res = media_client.post(
        "/media?kind=video&clip_type=std-video&plugin_id=not-a-real-plugin",
        headers=AUTH,
        files={"file": ("clip.mp4", io.BytesIO(b"x"), "video/mp4")},
    )
    assert res.status_code == 400
    assert "unknown" in res.json()["detail"]


def test_upload_without_clip_context_skips_manifest(media_client: TestClient, tmp_path):
    data = b"hello"
    res = media_client.post(
        "/media?kind=default",
        headers=AUTH,
        files={"file": ("plain.bin", io.BytesIO(data), "application/octet-stream")},
    )
    assert res.status_code == 200
    assert not (tmp_path / f"plain.bin{UPLOAD_MANIFEST_SUFFIX}").exists()


def test_upload_background_image_applies_policy(media_client: TestClient, tmp_path):
    from PIL import Image as PILImage

    rebuild_catalog_cache()
    buf = io.BytesIO()
    PILImage.new("RGB", (4000, 1200), color=(0, 128, 255)).save(buf, format="PNG")
    buf.seek(0)

    res = media_client.post(
        "/media?kind=image&clip_type=std-background-image&plugin_id=pixfabrica-std"
        "&target_width=1920&target_height=1080",
        headers=AUTH,
        files={"file": ("bg.png", buf, "image/png")},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["optimized_for"] == {"width": 2880, "height": 864, "fps": 0.0}

    saved = tmp_path / "bg.png"
    with PILImage.open(saved) as img:
        assert img.size == (2880, 864)

    manifest = tmp_path / f"bg.png{UPLOAD_MANIFEST_SUFFIX}"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["clip_type"] == "std-background-image"
    assert payload["optimized_for"]["width"] == 2880


def test_ingest_url_background_image(media_client: TestClient, tmp_path, monkeypatch):
    from PIL import Image as PILImage

    rebuild_catalog_cache()

    buf = io.BytesIO()
    PILImage.new("RGB", (5000, 5000), color=(255, 255, 0)).save(buf, format="PNG")
    remote_bytes = buf.getvalue()

    class _Response:
        def __init__(self):
            self.headers = {"content-length": str(len(remote_bytes))}

        def raise_for_status(self):
            return None

        def iter_bytes(self):
            yield remote_bytes

    class _StreamCtx:
        def __enter__(self):
            return _Response()

        def __exit__(self, *args):
            return False

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def stream(self, method, url):
            assert method == "GET"
            assert url.startswith("https://")
            return _StreamCtx()

    monkeypatch.setattr("pixfabrica_api.media_fetch.httpx.Client", _Client)

    res = media_client.post(
        "/media/ingest-url?kind=image&clip_type=std-background-image&plugin_id=pixfabrica-std"
        "&target_width=1080&target_height=1080",
        headers=AUTH,
        json={"url": "https://example.com/cover.png"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["optimized_for"] == {"width": 1620, "height": 1620, "fps": 0.0}
    saved = Path(body["path"])
    assert saved.is_file()
    with PILImage.open(saved) as img:
        assert img.size == (1620, 1620)

    res2 = media_client.post(
        "/media/ingest-url?kind=image&clip_type=std-background-image&plugin_id=pixfabrica-std"
        "&target_width=1080&target_height=1080",
        headers=AUTH,
        json={"url": "https://example.com/cover.png"},
    )
    assert res2.status_code == 200
    assert res2.json()["path"] == body["path"]


def test_upload_vinyl_record_applies_policy(media_client: TestClient, tmp_path):
    from PIL import Image as PILImage

    rebuild_catalog_cache()
    buf = io.BytesIO()
    PILImage.new("RGB", (4000, 4000), color=(200, 0, 0)).save(buf, format="PNG")
    buf.seek(0)

    res = media_client.post(
        "/media?kind=image&clip_type=std-vinyl-record&plugin_id=pixfabrica-std"
        "&target_width=1920&target_height=1080",
        headers=AUTH,
        files={"file": ("cover.png", buf, "image/png")},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["optimized_for"] == {"width": 921, "height": 921, "fps": 0.0}
    with PILImage.open(tmp_path / "cover.png") as img:
        assert img.size == (921, 921)


def test_upload_rejects_oversize(media_client: TestClient):
    huge = b"x" * (6 * 1024 * 1024)
    res = media_client.post(
        "/media?kind=lyrics",
        headers=AUTH,
        files={"file": ("big.lrc", io.BytesIO(huge), "text/plain")},
    )
    assert res.status_code == 413


def test_upload_video_rejects_without_ffmpeg(media_client: TestClient, monkeypatch):
    monkeypatch.setattr("pixfabrica_api.routes.media.video_ffmpeg_available", lambda: False)
    res = media_client.post(
        "/media?kind=video",
        headers=AUTH,
        files={"file": ("clip.mp4", io.BytesIO(b"x"), "video/mp4")},
    )
    assert res.status_code == 503


def test_fetch_nested_bundle_media_path(media_client: TestClient, tmp_path: Path):
    nested = tmp_path / "bundles" / "gallery" / "starters" / "demo"
    nested.mkdir(parents=True)
    audio = nested / "track.mp3"
    audio.write_bytes(b"nested-mp3")

    rel = audio.relative_to(tmp_path).as_posix()
    res = media_client.get(f"/media/{rel}", headers=AUTH)
    assert res.status_code == 200
    assert res.content == b"nested-mp3"


def test_fetch_nested_media_rejects_traversal(media_client: TestClient):
    res = media_client.get("/media/bundles/../secret.mp3", headers=AUTH)
    assert res.status_code in {400, 404}
