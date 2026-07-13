"""Unit tests for portable gallery media reference rewriting."""

from __future__ import annotations

from pathlib import Path

from pixfabrica_api.gallery_media import (
    is_portable_media_ref,
    resolve_portable_media_ref,
    rewrite_gallery_media_refs,
)


def test_is_portable_media_ref():
    assert is_portable_media_ref("media/cover.jpg")
    assert is_portable_media_ref("/media/snippet.mp3")
    assert not is_portable_media_ref("https://example.com/media/x.mp3")
    assert not is_portable_media_ref("/abs/path/cover.jpg")


def test_rewrite_nested_project(tmp_path: Path):
    media_root = tmp_path / "media"
    media_root.mkdir()
    cover = media_root / "cover.jpg"
    cover.write_bytes(b"jpg")

    project = {
        "tracks": [{"clips": [{"source": "media/cover.jpg"}]}],
        "sounds": [{"source": "/media/cover.jpg"}],
        "note": "not media/foo",
    }
    rewritten = rewrite_gallery_media_refs(project, media_root)
    expected = str(cover.resolve())
    assert rewritten["tracks"][0]["clips"][0]["source"] == expected
    assert rewritten["sounds"][0]["source"] == expected
    assert rewritten["note"] == "not media/foo"
    missing = resolve_portable_media_ref("media/missing.jpg", media_root)
    assert missing == str((media_root / "missing.jpg").resolve())
