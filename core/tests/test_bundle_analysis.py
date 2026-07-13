"""Bus timeline sidecars for project bundles."""

from __future__ import annotations

from pathlib import Path

from pixfabrica_core.audio.analysis import save_timeline_cache
from pixfabrica_core.audio.bundle_analysis import (
    collect_analysis_sidecars_for_export,
    hydrate_analysis_cache_from_manifest,
    sound_analysis_specs_for_bundled_sounds,
)
from pixfabrica_core.audio.bus import AudioBusFrame
from pixfabrica_core.audio.cache import timeline_cache_path_for_file


def test_export_and_import_hydrates_analysis_cache(tmp_path: Path) -> None:
    audio = tmp_path / "track.wav"
    audio.write_bytes(b"audio-bytes")
    cache_dir = tmp_path / "cache"

    spec = sound_analysis_specs_for_bundled_sounds(
        {
            "fps": 30.0,
            "sounds": [
                {
                    "id": "snd-1",
                    "analyzer": "stem",
                    "seek": 0.0,
                    "beat_tightness": 200.0,
                }
            ],
        },
        {0: (audio, "assets/track.wav")},
    )
    assert len(spec) == 1

    timeline = [AudioBusFrame.zero()]
    npz_path = spec[0].cache_path(cache_dir)
    npz_path.parent.mkdir(parents=True, exist_ok=True)
    save_timeline_cache(npz_path, timeline)

    manifest, files = collect_analysis_sidecars_for_export(spec, cache_dir=cache_dir)
    assert len(manifest) == 1
    assert manifest[0]["sidecar"] == "analysis/snd-1_stem.npz"
    assert files[0][1] == npz_path

    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    (bundle_dir / "track.wav").write_bytes(b"audio-bytes")
    import_cache = tmp_path / "import-cache"

    hydrated = hydrate_analysis_cache_from_manifest(
        manifest,
        bundle_dir=bundle_dir,
        cache_dir=import_cache,
        sidecar_bytes={files[0][0]: npz_path.read_bytes()},
    )
    assert hydrated == 1

    dest = timeline_cache_path_for_file(
        import_cache,
        bundle_dir / "track.wav",
        0.0,
        None,
        30.0,
        200.0,
    )
    assert dest.is_file()
