from pixfabrica_core.clips import JobInfo, PrepareContext
from pixfabrica_core.prepare_diagnostics import (
    PrepareDiagnostics,
    format_asset_error,
    prepare_warnings_event,
    record_prepare_asset_failure,
)
from pixfabrica_core.theme.color import ColorPalette
from pixfabrica_core.theme.typography import FontPalette


def _ctx(diag: PrepareDiagnostics) -> PrepareContext:
    job = JobInfo(
        title="t",
        description="",
        width=1920,
        height=1080,
        fps=30.0,
        duration=10.0,
        locale="en",
        colors=ColorPalette(),
        typography=FontPalette(),
    )
    return PrepareContext.from_env(job, diagnostics=diag)


def test_record_skips_empty_source() -> None:
    diag = PrepareDiagnostics()
    record_prepare_asset_failure(
        _ctx(diag),
        kind="clip",
        ref_id="el-1",
        clip_type="std-background-image",
        field="source",
        source="  ",
        exc=FileNotFoundError("missing"),
    )
    assert diag.items() == []


def test_prepare_warnings_event_wire() -> None:
    diag = PrepareDiagnostics()
    record_prepare_asset_failure(
        _ctx(diag),
        kind="clip",
        ref_id="el-1",
        clip_type="std-background-image",
        field="source",
        source="/bad/path.png",
        exc=FileNotFoundError("no file"),
    )
    payload = prepare_warnings_event(diag)
    assert payload["event"] == "prepare_warnings"
    assert len(payload["items"]) == 1
    assert payload["items"][0]["kind"] == "clip"
    assert payload["items"][0]["ref_id"] == "el-1"
    assert "no file" in payload["items"][0]["message"]


def test_format_asset_error_file_not_found() -> None:
    assert "missing" in format_asset_error(FileNotFoundError("missing"))
