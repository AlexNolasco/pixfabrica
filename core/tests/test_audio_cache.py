from pathlib import Path

from pixfabrica_core.audio.cache import timeline_cache_path_for_file


def test_timeline_cache_path_uses_stem_v2_signature(tmp_path: Path) -> None:
    audio = tmp_path / "tone.wav"
    audio.write_bytes(b"x")
    path_a = timeline_cache_path_for_file(tmp_path, audio, 0.0, None, 24.0, 200.0)
    path_b = timeline_cache_path_for_file(tmp_path, audio, 0.0, None, 24.0, 200.0)
    assert path_a == path_b
    assert "analysis_" in path_a.name
