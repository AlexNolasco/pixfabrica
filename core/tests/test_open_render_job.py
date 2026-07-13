"""Tests for portable project bundle import/export and open_render_job."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from pixfabrica_core.audio.analysis import save_timeline_cache
from pixfabrica_core.audio.bus import AudioBusFrame
from pixfabrica_core.audio.cache import timeline_cache_path_for_file
from pixfabrica_core.catalog import build_catalog_cache
from pixfabrica_core.composition.effect_registry import register_effect
from pixfabrica_core.composition.registry import register_clip_type, register_setting_type
from pixfabrica_core.errors import RenderError, RenderErrorCode
from pixfabrica_core.open_render_job import open_render_job
from pixfabrica_core.plugins.discovery import discover_plugins
from pixfabrica_core.project_bundles.errors import BundleExportError, BundleImportError
from pixfabrica_core.project_bundles.export import export_project_bundle
from pixfabrica_core.project_bundles.format import ASSETS_DIR, BUNDLE_MANIFEST_NAME
from pixfabrica_core.project_bundles.import_bundle import import_project_bundle


@pytest.fixture
def catalog():
    discovered, _ = discover_plugins()
    for plugin in discovered:
        for clip_cls in plugin.clip_types:
            register_clip_type(clip_cls)
        for cfg_cls in plugin.project_settings:
            register_setting_type(cfg_cls)
        for effect_cls in plugin.effects:
            register_effect(effect_cls)
    return build_catalog_cache(discovered)


def _minimal_project(*, source: str, remote: str | None = None) -> dict:
    project = {
        "schema_version": 1,
        "title": "Test Bundle",
        "description": "bundle test project",
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


def test_export_and_import_round_trip(tmp_path: Path, catalog) -> None:
    media_file = tmp_path / "cover.jpg"
    media_file.write_bytes(b"fake-image")
    source = str(media_file.resolve())
    project = _minimal_project(source=source)

    payload, filename = export_project_bundle(
        project,
        media_root=tmp_path,
        catalog=catalog,
    )
    assert filename == "Test Bundle.pixfabrica.zip"

    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        manifest = json.loads(archive.read(BUNDLE_MANIFEST_NAME))
        assert manifest["format"] == "pixfabrica-bundle"
        bundled_project = json.loads(archive.read("project.json"))
        assert bundled_project["tracks"][0]["clips"][0]["source"] == f"{ASSETS_DIR}/cover.jpg"
        assert "import_bundle_id" not in bundled_project
        assert archive.read(f"{ASSETS_DIR}/cover.jpg") == b"fake-image"

    bundle_dir = tmp_path / "imported"
    imported = import_project_bundle(
        payload,
        bundle_dir=bundle_dir,
        catalog=catalog,
    )
    local_source = imported["tracks"][0]["clips"][0]["source"]
    assert Path(local_source).is_file()
    assert imported["sounds"][0]["source"] == local_source
    assert "import_bundle_id" not in imported


def test_export_blocks_on_missing_files(tmp_path: Path, catalog) -> None:
    project = _minimal_project(source=str(Path("C:/missing/cover.jpg")))

    with pytest.raises(BundleExportError) as exc_info:
        export_project_bundle(project, media_root=tmp_path, catalog=catalog)

    assert exc_info.value.missing_files


def test_export_skips_remote_urls(tmp_path: Path, catalog) -> None:
    media_file = tmp_path / "cover.jpg"
    media_file.write_bytes(b"fake-image")
    project = _minimal_project(
        source=str(media_file.resolve()),
        remote="https://example.com/remote.mp3",
    )

    payload, _ = export_project_bundle(project, media_root=tmp_path, catalog=catalog)

    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        bundled = json.loads(archive.read("project.json"))
        remote_sound = next(s for s in bundled["sounds"] if s["id"] == "snd-remote")
        assert remote_sound["source"] == "https://example.com/remote.mp3"


def test_import_hydrates_analysis_cache_from_sidecar(tmp_path: Path, catalog, monkeypatch) -> None:
    cache_dir = tmp_path / "cache"
    monkeypatch.setenv("PIXFABRICA_CACHE_DIR", str(cache_dir))

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
        cache_dir,
        audio,
        0.0,
        None,
        30.0,
        200.0,
    )
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    save_timeline_cache(cache_file, [AudioBusFrame.zero()])

    payload, _ = export_project_bundle(project, media_root=tmp_path, catalog=catalog)
    cache_file.unlink()

    imported = import_project_bundle(
        payload,
        bundle_dir=tmp_path / "bundle",
        catalog=catalog,
    )
    imported_audio = Path(imported["sounds"][0]["source"])
    hydrated = timeline_cache_path_for_file(
        cache_dir,
        imported_audio,
        0.0,
        None,
        30.0,
        200.0,
    )
    assert hydrated.is_file()


def test_open_render_job_json_path(catalog, tmp_path: Path) -> None:
    job_path = tmp_path / "job.json"
    job_path.write_text(
        json.dumps(
            {
                "title": "JSON Job",
                "description": "plain json",
                "width": 640,
                "height": 360,
                "fps": 24,
                "duration": 1,
            }
        ),
        encoding="utf-8",
    )

    with open_render_job(job_path, catalog=catalog) as job:
        assert job.title == "JSON Job"
        assert job.width == 640


def test_open_render_job_bundle_path(tmp_path: Path, catalog) -> None:
    media_file = tmp_path / "cover.jpg"
    media_file.write_bytes(b"fake-image")
    project = _minimal_project(source=str(media_file.resolve()))
    payload, _ = export_project_bundle(project, media_root=tmp_path, catalog=catalog)
    bundle_path = tmp_path / "test.pixfabrica.zip"
    bundle_path.write_bytes(payload)

    asset_path = ""
    with open_render_job(bundle_path, catalog=catalog) as job:
        assert job.title == "Test Bundle"
        asset_path = str(getattr(job.tracks[0].clips[0], "source", ""))
        assert asset_path.endswith("cover.jpg")
        assert Path(asset_path).is_file()

    assert not Path(asset_path).is_file()


def test_open_render_job_rejects_invalid_zip(tmp_path: Path, catalog) -> None:
    bad_zip = tmp_path / "bad.zip"
    bad_zip.write_bytes(b"not-a-zip")

    with pytest.raises(RenderError) as exc_info, open_render_job(bad_zip, catalog=catalog):
        pass

    assert exc_info.value.code == RenderErrorCode.INVALID_PARAMETER


def test_import_rejects_invalid_zip(catalog, tmp_path: Path) -> None:
    with pytest.raises(BundleImportError, match="valid zip"):
        import_project_bundle(
            b"not-a-zip",
            bundle_dir=tmp_path / "bundle",
            catalog=catalog,
        )
