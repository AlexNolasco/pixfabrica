"""Tests for starter gallery routes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pixfabrica_api.catalog_cache import rebuild_catalog_cache
from pixfabrica_api.main import app
from pixfabrica_core.project_bundles.export import export_project_bundle

client = TestClient(app)
AUTH = {"Authorization": "Bearer pixfabrica-dev-token"}


@pytest.fixture
def gallery_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "gallery"
    root.mkdir()
    monkeypatch.setenv("PIXFABRICA_GALLERY_ROOT", str(root))
    return root


def _write_starter(
    root: Path,
    category: str,
    slug: str,
    *,
    title: str = "Cozy Night",
    description: str = "Warm campfire vibes",
) -> None:
    cat_dir = root / category
    cat_dir.mkdir(parents=True, exist_ok=True)
    (cat_dir / f"{slug}.json").write_text(
        json.dumps(
            {
                "title": title,
                "description": description,
                "width": 1920,
                "height": 1080,
                "fps": 30,
                "duration": 10,
                "tracks": [],
                "sounds": [],
            }
        ),
        encoding="utf-8",
    )
    (cat_dir / f"{slug}.webp").write_bytes(b"RIFFwebp")


def test_gallery_list_empty(gallery_root: Path):
    res = client.get("/gallery", headers=AUTH)
    assert res.status_code == 200
    assert res.json() == {"categories": []}


def test_gallery_list_and_detail(gallery_root: Path):
    _write_starter(gallery_root, "campfire", "cozy-night")

    res = client.get("/gallery", headers=AUTH)
    assert res.status_code == 200
    body = res.json()
    assert len(body["categories"]) == 1
    category = body["categories"][0]
    assert category["id"] == "campfire"
    assert category["label"] == "Campfire"
    assert len(category["items"]) == 1
    item = category["items"][0]
    assert item["id"] == "cozy-night"
    assert item["title"] == "Cozy Night"
    assert item["description"] == "Warm campfire vibes"
    assert item["thumbnail_url"].endswith("/gallery/thumbnails/campfire/cozy-night")

    detail = client.get("/gallery/campfire/cozy-night", headers=AUTH)
    assert detail.status_code == 200
    assert detail.json()["title"] == "Cozy Night"


def test_gallery_skips_incomplete_pair(gallery_root: Path):
    cat_dir = gallery_root / "waveforms"
    cat_dir.mkdir()
    (cat_dir / "no-thumb.json").write_text(
        json.dumps({"title": "X", "width": 100, "height": 100, "fps": 30, "duration": 1}),
        encoding="utf-8",
    )

    res = client.get("/gallery", headers=AUTH)
    assert res.status_code == 200
    assert res.json() == {"categories": []}


def test_gallery_thumbnail_public_without_auth(gallery_root: Path):
    _write_starter(gallery_root, "campfire", "cozy-night")

    res = client.get("/gallery/thumbnails/campfire/cozy-night")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("image/webp")


def test_gallery_detail_not_found(gallery_root: Path):
    res = client.get("/gallery/campfire/missing", headers=AUTH)
    assert res.status_code == 404


def test_gallery_resolves_portable_media_refs(
    gallery_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    media = tmp_path / "media"
    media.mkdir()
    snippet = media / "snippet.mp3"
    snippet.write_bytes(b"mp3")
    monkeypatch.setenv("PIXFABRICA_MEDIA_ROOT", str(media))

    cat_dir = gallery_root / "audio"
    cat_dir.mkdir(parents=True)
    (cat_dir / "demo.json").write_text(
        json.dumps(
            {
                "title": "Demo",
                "width": 1080,
                "height": 1920,
                "fps": 30,
                "duration": 10,
                "tracks": [
                    {
                        "clip_type": "std-skia-track",
                        "id": "track-1",
                        "clips": [
                            {
                                "clip_type": "std-background-image",
                                "id": "bg",
                                "source": "media/cover.jpg",
                            }
                        ],
                    }
                ],
                "sounds": [
                    {
                        "sound_type": "std-sound",
                        "id": "snd-1",
                        "bus": "main",
                        "source": "/media/snippet.mp3",
                    }
                ],
                "palette_source": {"type": "extracted", "filename": "media/cover.jpg"},
            }
        ),
        encoding="utf-8",
    )
    (cat_dir / "demo.webp").write_bytes(b"RIFFwebp")
    cover = media / "cover.jpg"
    cover.write_bytes(b"jpg")

    detail = client.get("/gallery/audio/demo", headers=AUTH)
    assert detail.status_code == 200
    body = detail.json()
    expected_snippet = str(snippet.resolve())
    expected_cover = str(cover.resolve())

    assert body["sounds"][0]["source"] == expected_snippet
    assert body["tracks"][0]["clips"][0]["source"] == expected_cover
    assert body["palette_source"]["filename"] == expected_cover


def test_gallery_publish_from_web(gallery_root: Path, tmp_path: Path, monkeypatch):
    media = tmp_path / "media"
    media.mkdir()
    monkeypatch.setenv("PIXFABRICA_GALLERY_ROOT", str(gallery_root))
    monkeypatch.setenv("PIXFABRICA_MEDIA_ROOT", str(media))
    monkeypatch.setenv("PIXFABRICA_GALLERY_PUBLISH", "1")
    # Vertical starter (1080×1920) — within local/compose limits, not hosted defaults.
    monkeypatch.setattr("pixfabrica_api.project_limits.MAX_HEIGHT", 2160)

    cover = media / "cover.jpg"
    cover.write_bytes(b"jpg")
    project = {
        "title": "Web Publish",
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "duration": 10,
        "tracks": [
            {
                "clip_type": "std-skia-track",
                "id": "track-1",
                "clips": [
                    {
                        "clip_type": "std-background-image",
                        "id": "bg",
                        "source": str(cover.resolve()),
                    }
                ],
            }
        ],
        "sounds": [],
    }
    thumb = tmp_path / "thumb.webp"
    thumb.write_bytes(b"RIFFwebp")

    res = client.post(
        "/gallery/publish",
        headers=AUTH,
        data={
            "category": "dev",
            "slug": "web-publish",
            "project": json.dumps(project),
        },
        files={"thumb": ("thumb.webp", thumb.read_bytes(), "image/webp")},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["category"] == "dev"
    assert body["slug"] == "web-publish"
    assert body["media_refs"] == []
    assert body["gallery_bundle"]
    meta = json.loads((gallery_root / "dev" / "web-publish.json").read_text(encoding="utf-8"))
    assert meta["title"] == "Web Publish"
    assert "tracks" not in meta
    assert (gallery_root / "dev" / "web-publish.pixfabrica.zip").is_file()


def test_gallery_publish_disabled(gallery_root: Path, tmp_path: Path, monkeypatch):
    monkeypatch.setenv("PIXFABRICA_GALLERY_ROOT", str(gallery_root))
    monkeypatch.setenv("PIXFABRICA_GALLERY_PUBLISH", "0")
    thumb = tmp_path / "thumb.webp"
    thumb.write_bytes(b"RIFFwebp")
    res = client.post(
        "/gallery/publish",
        headers=AUTH,
        data={
            "category": "dev",
            "slug": "blocked",
            "project": json.dumps(
                {"title": "X", "width": 1, "height": 1, "fps": 30, "duration": 1}
            ),
        },
        files={"thumb": ("thumb.webp", thumb.read_bytes(), "image/webp")},
    )
    assert res.status_code == 403


def test_gallery_leaves_remote_sources_unchanged(gallery_root: Path):
    cat_dir = gallery_root / "remote"
    cat_dir.mkdir(parents=True)
    remote = "https://example.com/track.mp3"
    (cat_dir / "remote.json").write_text(
        json.dumps(
            {
                "title": "Remote",
                "width": 1080,
                "height": 1920,
                "fps": 30,
                "duration": 10,
                "tracks": [],
                "sounds": [
                    {"sound_type": "std-sound", "id": "s1", "bus": "main", "source": remote}
                ],
            }
        ),
        encoding="utf-8",
    )
    (cat_dir / "remote.webp").write_bytes(b"RIFFwebp")

    detail = client.get("/gallery/remote/remote", headers=AUTH)
    assert detail.status_code == 200
    assert detail.json()["sounds"][0]["source"] == remote


def test_gallery_loads_bundle_starter(gallery_root: Path, tmp_path: Path, monkeypatch):
    media = tmp_path / "media"
    media.mkdir()
    monkeypatch.setenv("PIXFABRICA_MEDIA_ROOT", str(media))

    cover = media / "cover.jpg"
    cover.write_bytes(b"jpg")
    project = {
        "title": "Bundled",
        "description": "From zip",
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "duration": 10,
        "tracks": [
            {
                "clip_type": "std-skia-track",
                "id": "track-1",
                "clips": [
                    {
                        "clip_type": "std-background-image",
                        "id": "bg",
                        "source": str(cover.resolve()),
                    }
                ],
            }
        ],
        "sounds": [],
    }
    rebuild_catalog_cache()
    bundle_bytes, _ = export_project_bundle(
        project,
        media_root=media,
        catalog=rebuild_catalog_cache(),
    )

    cat_dir = gallery_root / "bundled"
    cat_dir.mkdir(parents=True)
    slug = "demo"
    (cat_dir / f"{slug}.json").write_text(
        json.dumps({"title": "Bundled", "description": "From zip"}),
        encoding="utf-8",
    )
    (cat_dir / f"{slug}.webp").write_bytes(b"RIFFwebp")
    (cat_dir / f"{slug}.pixfabrica.zip").write_bytes(bundle_bytes)

    list_res = client.get("/gallery", headers=AUTH)
    assert list_res.status_code == 200
    item = list_res.json()["categories"][0]["items"][0]
    assert item["title"] == "Bundled"

    detail = client.get("/gallery/bundled/demo", headers=AUTH)
    assert detail.status_code == 200
    body = detail.json()
    local_source = body["tracks"][0]["clips"][0]["source"]
    assert Path(local_source).is_file()
    assert local_source.startswith(str(media / "bundles" / "gallery"))


def test_gallery_bundle_audio_fetchable_via_nested_media_path(
    gallery_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    media = tmp_path / "media"
    media.mkdir()
    monkeypatch.setenv("PIXFABRICA_MEDIA_ROOT", str(media))

    audio = media / "beat.mp3"
    audio.write_bytes(b"gallery-mp3")
    project = {
        "title": "Audio Bundled",
        "description": "With sound",
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "duration": 10,
        "tracks": [],
        "sounds": [
            {
                "sound_type": "std-sound",
                "id": "snd-1",
                "bus": "main",
                "source": str(audio.resolve()),
            }
        ],
    }
    rebuild_catalog_cache()
    bundle_bytes, _ = export_project_bundle(
        project,
        media_root=media,
        catalog=rebuild_catalog_cache(),
    )

    cat_dir = gallery_root / "audio"
    cat_dir.mkdir(parents=True)
    slug = "demo"
    (cat_dir / f"{slug}.json").write_text(
        json.dumps({"title": "Audio Bundled", "description": "With sound"}),
        encoding="utf-8",
    )
    (cat_dir / f"{slug}.webp").write_bytes(b"RIFFwebp")
    (cat_dir / f"{slug}.pixfabrica.zip").write_bytes(bundle_bytes)

    detail = client.get("/gallery/audio/demo", headers=AUTH)
    assert detail.status_code == 200
    body = detail.json()
    sound_source = body["sounds"][0]["source"]
    sound_path = Path(sound_source)
    assert sound_path.is_file()
    assert sound_path.is_relative_to(media / "bundles" / "gallery")

    rel = sound_path.relative_to(media).as_posix()
    fetch = client.get(f"/media/{rel}", headers=AUTH)
    assert fetch.status_code == 200
    assert fetch.content == b"gallery-mp3"
