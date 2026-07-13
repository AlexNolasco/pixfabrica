"""RenderJob palette_source metadata."""

from __future__ import annotations

from pixfabrica_core.clips import RenderJob
from pixfabrica_core.theme.color import ColorPalette
from pixfabrica_core.theme.palette_source import NamedPaletteSource


def test_render_job_roundtrips_palette_source() -> None:
    job = RenderJob.model_validate(
        {
            "title": "t",
            "description": "d",
            "colors": ColorPalette().model_dump(mode="json"),
            "palette_source": {"type": "named", "theme": "amber", "variant": "dark"},
            "tracks": [],
        }
    )
    assert isinstance(job.palette_source, NamedPaletteSource)
    assert job.palette_source.theme == "amber"

    payload = job.model_dump(mode="json")
    restored = RenderJob.model_validate(payload)
    assert restored.palette_source is not None
    assert restored.palette_source.type == "named"
