"""Tests for gallery publish helpers."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from pixfabrica_api.catalog_cache import rebuild_catalog_cache
from pixfabrica_api.gallery_publish import (
    GalleryPublishError,
    publish_bundle_to_gallery,
    publish_json_to_gallery,
)
from pixfabrica_api.gallery_scan import gallery_bundle_filename
from pixfabrica_core.project_bundles.export import export_project_bundle
from pixfabrica_core.project_bundles.format import PROJECT_JSON_NAME


@pytest.fixture
def publish_roots(tmp_path: Path):
    gallery = tmp_path / "gallery"
    media = tmp_path / "media"
    gallery.mkdir()
    media.mkdir()
    return gallery, media


def test_publish_json_writes_bundle_and_metadata(publish_roots: tuple[Path, Path]):
    gallery, media = publish_roots
    cover = media / "cover.jpg"
    cover.write_bytes(b"jpg")
    project = {
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
                        "source": str(cover.resolve()),
                    }
                ],
            }
        ],
        "sounds": [],
    }
    thumb = gallery / "thumb.webp"
    thumb.write_bytes(b"RIFFwebp")

    rebuild_catalog_cache()
    result = publish_json_to_gallery(
        project,
        category="campfire",
        slug="demo",
        thumb_src=thumb,
        gallery_root=gallery,
        media_root=media,
        catalog=rebuild_catalog_cache(),
    )

    bundle_path = gallery / "campfire" / gallery_bundle_filename("demo")
    meta_path = gallery / "campfire" / "demo.json"
    assert bundle_path.is_file()
    assert meta_path.is_file()
    assert result.gallery_bundle == bundle_path.resolve()

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta == {"title": "Demo", "description": ""}
    assert (gallery / "campfire" / "demo.webp").is_file()
    assert result.media_refs == ()

    with zipfile.ZipFile(bundle_path) as archive:
        bundled = json.loads(archive.read(PROJECT_JSON_NAME))
    assert bundled["tracks"][0]["clips"][0]["source"].startswith("assets/")


def test_publish_bundle_round_trip(publish_roots: tuple[Path, Path], tmp_path: Path):
    gallery, media = publish_roots
    cover = media / "cover.jpg"
    cover.write_bytes(b"jpg")
    project = {
        "title": "Bundle Demo",
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
    bundle_path = tmp_path / "demo.pixfabrica.zip"
    bundle_path.write_bytes(bundle_bytes)
    thumb = tmp_path / "thumb.png"
    thumb.write_bytes(b"\x89PNG")

    result = publish_bundle_to_gallery(
        bundle_path,
        category="waveforms",
        slug="bundle-demo",
        thumb_src=thumb,
        gallery_root=gallery,
    )

    assert (gallery / "waveforms" / gallery_bundle_filename("bundle-demo")).is_file()
    meta = json.loads((gallery / "waveforms" / "bundle-demo.json").read_text(encoding="utf-8"))
    assert meta["title"] == "Bundle Demo"
    assert (gallery / "waveforms" / "bundle-demo.png").is_file()
    assert result.gallery_bundle is not None


def test_publish_rejects_invalid_slug(publish_roots: tuple[Path, Path]):
    gallery, media = publish_roots
    thumb = gallery / "thumb.webp"
    thumb.write_bytes(b"x")
    with pytest.raises(GalleryPublishError):
        publish_json_to_gallery(
            {"title": "X", "width": 1, "height": 1, "fps": 30, "duration": 1},
            category="bad slug",
            slug="demo",
            thumb_src=thumb,
            gallery_root=gallery,
            media_root=media,
            catalog=rebuild_catalog_cache(),
        )
