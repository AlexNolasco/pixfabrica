"""Background audio analysis API."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from pixfabrica_api.audio_analyze_service import AudioAnalyzeService
from pixfabrica_api.main import app
from pixfabrica_core.audio.analysis import AnalyzerKind
from pixfabrica_core.audio.cache import timeline_cache_path_for_file

AUTH = {"Authorization": "Bearer pixfabrica-dev-token"}
client = TestClient(app)


@pytest.mark.asyncio
async def test_start_stem_returns_done_when_cache_exists(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PIXFABRICA_CACHE_DIR", str(tmp_path / "cache"))
    audio = tmp_path / "tone.wav"
    audio.write_bytes(b"x")
    cache = timeline_cache_path_for_file(
        tmp_path / "cache",
        audio,
        0.0,
        None,
        30.0,
        200.0,
    )
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(b"npz")

    monkeypatch.setattr(
        "pixfabrica_api.audio_analyze_service._resolve_source",
        AsyncMock(return_value=audio),
    )

    service = AudioAnalyzeService()
    job = await service.start(
        source=str(audio),
        seek=0.0,
        duration=None,
        fps=30.0,
        beat_tightness=200.0,
        analyzer=AnalyzerKind.STEM,
    )
    assert job.status.value == "done"
    assert job.progress == 1.0


def test_start_audio_analyze_accepts_stem_analyzer(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PIXFABRICA_CACHE_DIR", str(tmp_path / "cache"))
    audio = tmp_path / "tone.wav"
    audio.write_bytes(b"x")
    cache = timeline_cache_path_for_file(
        tmp_path / "cache",
        audio,
        0.0,
        None,
        30.0,
        200.0,
    )
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(b"npz")

    monkeypatch.setattr(
        "pixfabrica_api.audio_analyze_service._resolve_source",
        AsyncMock(return_value=audio),
    )

    response = client.post(
        "/audio/analyze",
        json={
            "source": str(audio),
            "seek": 0.0,
            "duration": None,
            "fps": 30.0,
            "beat_tightness": 200.0,
            "analyzer": "stem",
        },
        headers=AUTH,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "done"
