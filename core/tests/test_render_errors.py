"""Tests for RenderError, load_render_job, and localised error formatting."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pixfabrica_core.errors import RenderError, RenderErrorCode
from pixfabrica_core.load_render_job import load_render_job

# ── Minimal valid job JSON ────────────────────────────────────────────────────

_VALID_JOB = {
    "title": "Test",
    "description": "Unit test job",
    "tracks": [],
}


def _write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


# ── RenderError ───────────────────────────────────────────────────────────────


def test_render_error_has_code_and_context():
    err = RenderError(RenderErrorCode.UNKNOWN_PLUGIN, {"clip_type": "acme-rain"})
    assert err.code == RenderErrorCode.UNKNOWN_PLUGIN
    assert err.context["clip_type"] == "acme-rain"


def test_render_error_format_en():
    err = RenderError(RenderErrorCode.UNKNOWN_PLUGIN, {"clip_type": "acme-rain"})
    msg = err.format("en")
    assert "acme-rain" in msg


def test_render_error_format_falls_back_to_en_for_unknown_locale():
    err = RenderError(RenderErrorCode.CANCELLED)
    msg = err.format("xx-UNKNOWN")
    assert msg  # at minimum returns something non-empty


def test_render_error_format_all_codes():
    cases = [
        (RenderErrorCode.UNKNOWN_PLUGIN, {"clip_type": "x"}),
        (RenderErrorCode.INVALID_PARAMETER, {"field": "fps", "msg": "too high"}),
        (RenderErrorCode.MISSING_ASSET, {"path": "/a/b.wav", "detail": "not found"}),
        (RenderErrorCode.FFMPEG_FAILURE, {"detail": "exit 1"}),
        (RenderErrorCode.ANALYSIS_FAILED, {"source": "song.wav", "detail": "corrupt"}),
        (RenderErrorCode.CANCELLED, {}),
        (RenderErrorCode.OUTPUT_WRITE_ERROR, {"path": "/out.mp4", "detail": "no space"}),
    ]
    for code, ctx in cases:
        msg = RenderError(code, ctx).format("en")
        assert isinstance(msg, str) and len(msg) > 0


# ── load_render_job ───────────────────────────────────────────────────────────


def test_load_valid_job(tmp_path):
    f = _write(tmp_path / "job.json", json.dumps(_VALID_JOB))
    job = load_render_job(f)
    assert job.title == "Test"
    assert job.tracks == []


def test_load_missing_file_raises_missing_asset(tmp_path):
    with pytest.raises(RenderError) as exc_info:
        load_render_job(tmp_path / "nonexistent.json")
    assert exc_info.value.code == RenderErrorCode.MISSING_ASSET


def test_load_invalid_json_raises_invalid_parameter(tmp_path):
    f = _write(tmp_path / "bad.json", "{ not valid json }")
    with pytest.raises(RenderError) as exc_info:
        load_render_job(f)
    assert exc_info.value.code == RenderErrorCode.INVALID_PARAMETER


def test_load_invalid_schema_raises_invalid_parameter(tmp_path):
    bad = {**_VALID_JOB, "fps": -5}  # fps has gt=0 constraint
    f = _write(tmp_path / "bad_schema.json", json.dumps(bad))
    with pytest.raises(RenderError) as exc_info:
        load_render_job(f)
    assert exc_info.value.code == RenderErrorCode.INVALID_PARAMETER
    assert "fps" in exc_info.value.context["field"]


def test_load_wrong_schema_version_raises_mismatch(tmp_path):
    f = _write(tmp_path / "future.json", json.dumps({**_VALID_JOB, "schema_version": 99}))
    with pytest.raises(RenderError) as exc_info:
        load_render_job(f)
    assert exc_info.value.code == RenderErrorCode.SCHEMA_VERSION_MISMATCH
    assert exc_info.value.context["job_version"] == 99


def test_load_missing_required_field_raises_invalid_parameter(tmp_path):
    f = _write(tmp_path / "no_title.json", json.dumps({"tracks": []}))
    with pytest.raises(RenderError) as exc_info:
        load_render_job(f)
    assert exc_info.value.code == RenderErrorCode.INVALID_PARAMETER


# ── Unknown plugin detection ──────────────────────────────────────────────────


def test_load_with_unknown_clip_type_produces_unknown_clip(tmp_path):
    """After load, unknown clip types become UnknownClip (not yet a hard error)."""
    from pixfabrica_core.composition.unknown import UnknownClip

    job_data = {
        **_VALID_JOB,
        "tracks": [
            {
                "clip_type": "std-skia-track",
                "id": "t1",
                "start": 0.0,
                "clips": [{"clip_type": "nonexistent-plugin-clip", "id": "e1", "start": 0.0}],
            }
        ],
    }
    f = _write(tmp_path / "unknown.json", json.dumps(job_data))
    job = load_render_job(f)
    assert any(isinstance(el, UnknownClip) for track in job.tracks for el in track.clips)
