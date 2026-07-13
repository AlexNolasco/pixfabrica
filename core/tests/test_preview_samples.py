"""CI guard for checked-in clip preview sample bundle."""

from __future__ import annotations

import pytest

from pixfabrica_core.audio.preview_samples import (
    find_web_public,
    load_sources,
    resolve_source_path,
    verify_shipped_samples,
)


def test_preview_samples_bundle_complete() -> None:
    public = find_web_public()
    sources = load_sources(public)
    assert len(sources) >= 3, "sources.json should list at least drums, symphony, ambient"

    missing = [s.id for s in sources if not resolve_source_path(public, s).is_file()]
    if missing:
        pytest.skip(
            "source mp3 not in tree yet "
            f"({', '.join(missing)}); add under preview-samples/sources/ and run "
            "`pixfabrica web bake-preview-samples`"
        )

    issues = verify_shipped_samples(public)
    assert not issues, "preview sample bundle incomplete:\n" + "\n".join(f"  - {i}" for i in issues)
