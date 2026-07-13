import json
from pathlib import Path

from pixfabrica_core.upload_manifest import (
    UPLOAD_MANIFEST_SUFFIX,
    read_upload_manifest,
    upload_manifest_path,
    write_upload_manifest,
)


def test_write_upload_manifest(tmp_path: Path):
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"video-bytes")

    manifest = write_upload_manifest(
        media,
        clip_type="std-video",
        plugin_id="pixfabrica-std",
        kind="video",
        size=11,
        content_sha256="abc123",
        optimized_for={"width": 640, "height": 360, "fps": 24.0},
    )

    assert manifest == upload_manifest_path(media)
    assert manifest.name == f"clip.mp4{UPLOAD_MANIFEST_SUFFIX}"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["clip_type"] == "std-video"
    assert payload["plugin_id"] == "pixfabrica-std"
    assert payload["kind"] == "video"
    assert payload["size"] == 11
    assert payload["content_sha256"] == "abc123"
    assert payload["optimized_for"] == {"width": 640, "height": 360, "fps": 24.0}
    assert "uploaded_at" in payload


def test_read_upload_manifest(tmp_path: Path):
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"video-bytes")
    write_upload_manifest(
        media,
        clip_type="std-video",
        plugin_id="pixfabrica-std",
        kind="video",
        size=11,
        content_sha256="abc123",
    )
    payload = read_upload_manifest(media)
    assert payload is not None
    assert payload["clip_type"] == "std-video"
