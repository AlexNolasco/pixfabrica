"""Tests for render job routes and disk persistence."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pixfabrica_api.job_service import job_service
from pixfabrica_api.main import app
from pixfabrica_core.progress import RenderProgress

AUTH = {"Authorization": "Bearer pixfabrica-dev-token"}

HELLO_GRAPH: dict = {
    "title": "Hello, World!",
    "description": "Minimal render example — solid background + centred text.",
    "width": 1280,
    "height": 720,
    "fps": 24.0,
    "duration": 5.0,
    "tracks": [
        {
            "clip_type": "std-skia-track",
            "id": "track-1",
            "start": 0.0,
            "clips": [
                {
                    "clip_type": "std-solid-background",
                    "id": "bg-1",
                    "start": 0.0,
                    "color": "background",
                },
                {
                    "clip_type": "std-static-text",
                    "id": "text-1",
                    "start": 0.0,
                    "text": "Hello, World!",
                    "color": "neutral",
                    "typography_role": "title_large",
                    "offset_x": 0.5,
                    "offset_y": 0.5,
                    "align": "center",
                },
            ],
        }
    ],
}


@pytest.fixture
def jobs_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("PIXFABRICA_JOBS_ROOT", str(tmp_path))
    job_service.recover_on_startup()
    return tmp_path


@pytest.fixture
def client(jobs_root: Path) -> Iterator[TestClient]:
    del jobs_root  # ensure jobs_root runs before lifespan starts the worker
    with TestClient(app) as test_client:
        yield test_client


async def _fake_render_job(*args, **_kwargs) -> AsyncIterator[RenderProgress]:
    yield RenderProgress(stage="prepare", frame=0, total=10, pct=0)
    yield RenderProgress(stage="render", frame=5, total=10, pct=50, parallelism_effective="single")
    output: Path = args[1]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b"\x00" * 8)
    yield RenderProgress(stage="done", frame=10, total=10, pct=100)


def _fake_discord_export(job_dir: Path, *, max_mb: int = 8) -> Path:
    out = job_dir / f"discord-export-{max_mb}.mp4"
    out.write_bytes(b"\x00" * 4)
    return out


def test_discord_export_route_errors(
    client: TestClient,
    jobs_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("pixfabrica_api.job_service.render_job", _fake_render_job)
    job_id = client.post("/jobs", json={"graph": HELLO_GRAPH}, headers=AUTH).json()["job_id"]
    _wait_for_terminal(client, job_id)

    monkeypatch.setattr("pixfabrica_api.routes.jobs.ffmpeg_available", lambda: False)
    no_ffmpeg = client.get(f"/jobs/{job_id}/video/discord", headers=AUTH)
    assert no_ffmpeg.status_code == 503

    monkeypatch.setattr("pixfabrica_api.routes.jobs.ffmpeg_available", lambda: True)

    def _too_large(_path: Path, *, max_mb: int = 8) -> Path:
        from pixfabrica_api.job_discord_export import DiscordExportTooLargeError

        raise DiscordExportTooLargeError("too long for Discord")

    monkeypatch.setattr("pixfabrica_api.routes.jobs.export_discord_video", _too_large)
    too_large = client.get(f"/jobs/{job_id}/video/discord", headers=AUTH)
    assert too_large.status_code == 422
    assert "too long" in too_large.json()["detail"]


def _wait_for_terminal(client: TestClient, job_id: str, *, timeout_s: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout_s
    last: dict = {}
    while time.monotonic() < deadline:
        res = client.get(f"/jobs/{job_id}", headers=AUTH)
        assert res.status_code == 200
        last = res.json()
        if last["status"] in {"done", "cancelled", "failed", "interrupted"}:
            return last
        time.sleep(0.05)
    pytest.fail(
        f"job {job_id} did not finish: last status={last.get('status')!r} error={last.get('error')!r}"
    )


def test_create_list_and_remove_job(
    client: TestClient,
    jobs_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("pixfabrica_api.job_service.render_job", _fake_render_job)

    create = client.post("/jobs", json={"graph": HELLO_GRAPH}, headers=AUTH)
    assert create.status_code == 200
    job_id = create.json()["job_id"]
    assert (jobs_root / job_id / "graph.json").is_file()
    assert (jobs_root / job_id / "metadata.json").is_file()

    listed = client.get("/jobs", headers=AUTH)
    assert listed.status_code == 200
    assert any(row["id"] == job_id for row in listed.json())

    detail = _wait_for_terminal(client, job_id)
    assert detail["status"] == "done"
    assert detail["render_parallelism_requested"] == "single"
    assert detail["render_parallelism_effective"] == "single"

    monkeypatch.setattr("pixfabrica_api.routes.jobs.ffmpeg_available", lambda: True)
    video = client.get(f"/jobs/{job_id}/video", headers=AUTH)
    assert video.status_code == 200

    monkeypatch.setattr(
        "pixfabrica_api.routes.jobs.export_discord_video",
        lambda path, *, max_mb=8: _fake_discord_export(path.parent, max_mb=max_mb),
    )
    discord = client.get(f"/jobs/{job_id}/video/discord", headers=AUTH)
    assert discord.status_code == 200
    assert "discord.mp4" in discord.headers["content-disposition"]

    nitro = client.get(f"/jobs/{job_id}/video/discord?max_mb=50", headers=AUTH)
    assert nitro.status_code == 200
    assert "discord-50mb.mp4" in nitro.headers["content-disposition"]

    removed = client.delete(f"/jobs/{job_id}/artifacts", headers=AUTH)
    assert removed.status_code == 200
    assert not (jobs_root / job_id).exists()


def test_cancel_queued_job(
    client: TestClient,
    jobs_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    blocked = threading.Event()

    async def _slow_render(*_args, **_kwargs) -> AsyncIterator[RenderProgress]:
        yield RenderProgress(stage="prepare", frame=0, total=1, pct=0)
        blocked.wait(timeout=30)
        yield RenderProgress(stage="done", frame=1, total=1, pct=100)

    monkeypatch.setattr("pixfabrica_api.job_service.render_job", _slow_render)

    first = client.post("/jobs", json={"graph": HELLO_GRAPH}, headers=AUTH).json()["job_id"]
    second = client.post("/jobs", json={"graph": HELLO_GRAPH}, headers=AUTH).json()["job_id"]

    cancel = client.delete(f"/jobs/{second}", headers=AUTH)
    assert cancel.status_code == 200

    detail = client.get(f"/jobs/{second}", headers=AUTH)
    assert detail.json()["status"] == "cancelled"

    remove = client.delete(f"/jobs/{second}/artifacts", headers=AUTH)
    assert remove.status_code == 200
    assert not (jobs_root / second).exists()

    client.delete(f"/jobs/{first}", headers=AUTH)
    blocked.set()
    client.delete(f"/jobs/{first}/artifacts", headers=AUTH)


def test_render_parallelism_persisted_on_first_frame(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _multi_fallback_render(*_args, **_kwargs) -> AsyncIterator[RenderProgress]:
        yield RenderProgress(stage="prepare", frame=0, total=10, pct=0)
        yield RenderProgress(
            stage="render", frame=1, total=10, pct=10, parallelism_effective="single"
        )
        output: Path = _args[1]
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"\x00" * 8)
        yield RenderProgress(stage="done", frame=10, total=10, pct=100)

    monkeypatch.setattr("pixfabrica_api.job_service.render_job", _multi_fallback_render)

    graph = {**HELLO_GRAPH, "parallelism": "multi"}
    job_id = client.post("/jobs", json={"graph": graph}, headers=AUTH).json()["job_id"]
    detail = _wait_for_terminal(client, job_id)
    assert detail["render_parallelism_requested"] == "multi"
    assert detail["render_parallelism_effective"] == "single"


def test_startup_marks_interrupted(jobs_root: Path) -> None:
    job_id = "test-interrupted"
    job_dir = jobs_root / job_id
    job_dir.mkdir()
    (job_dir / "graph.json").write_text(json.dumps(HELLO_GRAPH), encoding="utf-8")
    (job_dir / "metadata.json").write_text(
        json.dumps(
            {
                "id": job_id,
                "status": "rendering",
                "created_at": "2026-01-01T00:00:00+00:00",
                "title": "Test",
                "width": 1920,
                "height": 1080,
                "fps": 30,
                "duration_s": 1.0,
                "submitted_by": None,
                "executor": "local",
            }
        ),
        encoding="utf-8",
    )

    job_service.recover_on_startup()
    meta = json.loads((job_dir / "metadata.json").read_text(encoding="utf-8"))
    assert meta["status"] == "interrupted"
