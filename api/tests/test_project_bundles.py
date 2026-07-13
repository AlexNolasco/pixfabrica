"""Tests for project bundle export/import routes."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pixfabrica_api.catalog_cache import rebuild_catalog_cache
from pixfabrica_api.main import app
from pixfabrica_core.audio.analysis import save_timeline_cache
from pixfabrica_core.audio.bus import AudioBusFrame
from pixfabrica_core.audio.cache import timeline_cache_path_for_file
from pixfabrica_core.project_bundles.format import ASSETS_DIR, BUNDLE_MANIFEST_NAME

AUTH = {"Authorization": "Bearer pixfabrica-dev-token"}


@pytest.fixture
def bundle_client(tmp_path, monkeypatch):
    monkeypatch.setenv("PIXFABRICA_MEDIA_ROOT", str(tmp_path))
    monkeypatch.setenv("PIXFABRICA_CACHE_DIR", str(tmp_path / "cache"))
    rebuild_catalog_cache()
    return TestClient(app)


def _minimal_project(*, source: str, remote: str | None = None) -> dict:
    project = {
        "schema_version": 1,
        "title": "Test Bundle",
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "duration": 10,
        "timeline_layout": [{"kind": "track", "id": "track-1"}],
        "tracks": [
            {
                "clip_type": "std-skia-track",
                "id": "track-1",
                "clips": [
                    {
                        "clip_type": "std-background-image",
                        "id": "el-1",
                        "source": source,
                    }
                ],
            }
        ],
        "sounds": [
            {
                "sound_type": "std-sound",
                "id": "snd-1",
                "bus": "main",
                "source": source,
            }
        ],
        "palette_source": {"type": "extracted", "filename": source},
    }
    if remote is not None:
        project["sounds"].append(
            {
                "sound_type": "std-sound",
                "id": "snd-remote",
                "bus": "main",
                "source": remote,
            }
        )
    return project


def test_export_and_import_round_trip(bundle_client: TestClient, tmp_path: Path):
    media_file = tmp_path / "cover.jpg"
    media_file.write_bytes(b"fake-image")
    source = str(media_file.resolve())
    project = _minimal_project(source=source)

    export_res = bundle_client.post("/project-bundles/export", headers=AUTH, json=project)
    assert export_res.status_code == 200
    assert export_res.headers["content-type"] == "application/zip"
    assert "Test Bundle.pixfabrica.zip" in export_res.headers["content-disposition"]

    with zipfile.ZipFile(io.BytesIO(export_res.content)) as archive:
        manifest = json.loads(archive.read(BUNDLE_MANIFEST_NAME))
        assert manifest["format"] == "pixfabrica-bundle"
        bundled_project = json.loads(archive.read("project.json"))
        assert bundled_project["tracks"][0]["clips"][0]["source"] == f"{ASSETS_DIR}/cover.jpg"
        assert bundled_project["sounds"][0]["source"] == f"{ASSETS_DIR}/cover.jpg"
        assert "import_bundle_id" not in bundled_project
        assert archive.read(f"{ASSETS_DIR}/cover.jpg") == b"fake-image"

    import_res = bundle_client.post(
        "/project-bundles/import",
        headers=AUTH,
        files={
            "file": (
                "Test Bundle.pixfabrica.zip",
                io.BytesIO(export_res.content),
                "application/zip",
            )
        },
    )
    assert import_res.status_code == 200
    body = import_res.json()
    import_id = body["import_bundle_id"]
    imported = body["project"]
    assert import_id
    assert (tmp_path / "bundles" / import_id / "cover.jpg").is_file()

    local_source = imported["tracks"][0]["clips"][0]["source"]
    assert Path(local_source).is_file()
    assert imported["sounds"][0]["source"] == local_source
    assert imported["palette_source"]["filename"] == local_source
    assert imported["timeline_layout"] == [{"kind": "track", "id": "track-1"}]
    assert "import_bundle_id" not in imported


def test_export_blocks_on_missing_files(bundle_client: TestClient):
    project = _minimal_project(source=str(Path("C:/missing/cover.jpg")))

    res = bundle_client.post("/project-bundles/export", headers=AUTH, json=project)
    assert res.status_code == 400
    detail = res.json()["detail"]
    assert detail["code"] == "missing_assets"
    assert detail["missing_files"]


def test_export_skips_remote_urls(bundle_client: TestClient, tmp_path: Path):
    media_file = tmp_path / "cover.jpg"
    media_file.write_bytes(b"fake-image")
    project = _minimal_project(
        source=str(media_file.resolve()),
        remote="https://example.com/remote.mp3",
    )

    res = bundle_client.post("/project-bundles/export", headers=AUTH, json=project)
    assert res.status_code == 200

    with zipfile.ZipFile(io.BytesIO(res.content)) as archive:
        bundled = json.loads(archive.read("project.json"))
        remote_sound = next(s for s in bundled["sounds"] if s["id"] == "snd-remote")
        assert remote_sound["source"] == "https://example.com/remote.mp3"


def test_export_deduplicates_identical_assets(bundle_client: TestClient, tmp_path: Path):
    media_file = tmp_path / "cover.jpg"
    media_file.write_bytes(b"same-bytes")
    source = str(media_file.resolve())
    project = _minimal_project(source=source)

    res = bundle_client.post("/project-bundles/export", headers=AUTH, json=project)
    assert res.status_code == 200

    with zipfile.ZipFile(io.BytesIO(res.content)) as archive:
        asset_names = [name for name in archive.namelist() if name.startswith(f"{ASSETS_DIR}/")]
        assert asset_names == [f"{ASSETS_DIR}/cover.jpg"]


def test_export_includes_analysis_sidecar_when_cached(
    bundle_client: TestClient, tmp_path: Path
) -> None:
    audio = tmp_path / "beat.wav"
    audio.write_bytes(b"wav-bytes-for-analysis")
    source = str(audio.resolve())
    project = {
        **_minimal_project(source=source),
        "sounds": [
            {
                "sound_type": "std-sound",
                "id": "snd-1",
                "bus": "main",
                "source": source,
                "analyzer": "fast",
                "seek": 0.0,
                "beat_tightness": 200.0,
            }
        ],
    }

    cache_file = timeline_cache_path_for_file(
        tmp_path / "cache",
        audio,
        0.0,
        None,
        30.0,
        200.0,
    )
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    save_timeline_cache(cache_file, [AudioBusFrame.zero()])

    res = bundle_client.post("/project-bundles/export", headers=AUTH, json=project)
    assert res.status_code == 200

    with zipfile.ZipFile(io.BytesIO(res.content)) as archive:
        manifest = json.loads(archive.read(BUNDLE_MANIFEST_NAME))
        assert manifest.get("analysis_dir") == "analysis"
        analysis = manifest.get("analysis")
        assert isinstance(analysis, list) and len(analysis) == 1
        sidecar = analysis[0]["sidecar"]
        assert archive.read(sidecar)


def test_import_hydrates_analysis_cache_from_sidecar(
    bundle_client: TestClient, tmp_path: Path
) -> None:
    audio = tmp_path / "beat.wav"
    audio.write_bytes(b"wav-bytes-for-analysis")
    source = str(audio.resolve())
    project = {
        **_minimal_project(source=source),
        "sounds": [
            {
                "sound_type": "std-sound",
                "id": "snd-1",
                "bus": "main",
                "source": source,
                "analyzer": "fast",
            }
        ],
    }

    cache_file = timeline_cache_path_for_file(
        tmp_path / "cache",
        audio,
        0.0,
        None,
        30.0,
        200.0,
    )
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    save_timeline_cache(cache_file, [AudioBusFrame.zero()])

    export_res = bundle_client.post("/project-bundles/export", headers=AUTH, json=project)
    assert export_res.status_code == 200
    cache_file.unlink()

    import_res = bundle_client.post(
        "/project-bundles/import",
        headers=AUTH,
        files={
            "file": (
                "bundle.pixfabrica.zip",
                io.BytesIO(export_res.content),
                "application/zip",
            )
        },
    )
    assert import_res.status_code == 200
    imported_audio = Path(import_res.json()["project"]["sounds"][0]["source"])
    hydrated = timeline_cache_path_for_file(
        tmp_path / "cache",
        imported_audio,
        0.0,
        None,
        30.0,
        200.0,
    )
    assert hydrated.is_file()


def test_import_rejects_invalid_zip(bundle_client: TestClient):
    res = bundle_client.post(
        "/project-bundles/import",
        headers=AUTH,
        files={"file": ("bad.pixfabrica.zip", io.BytesIO(b"not-a-zip"), "application/zip")},
    )
    assert res.status_code == 400
