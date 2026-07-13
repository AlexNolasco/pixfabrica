from pathlib import Path

from pixfabrica_core.audio.content_hash import (
    audio_content_sidecar_path,
    content_sha256_for_path,
    write_audio_content_sidecar,
)


def test_sidecar_avoids_rehash(tmp_path: Path) -> None:
    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"abc")

    write_audio_content_sidecar(audio, content_sha256="a" * 64, size=3)
    assert content_sha256_for_path(audio) == "a" * 64

    audio.write_bytes(b"changed")
    # Size mismatch → re-hash
    digest = content_sha256_for_path(audio)
    assert digest != "a" * 64
    assert len(digest) == 64
    sidecar = audio_content_sidecar_path(audio)
    assert sidecar.is_file()
