from pixfabrica_core.preview_dims import (
    MAX_PREVIEW_LONG_SIDE,
    preview_dimensions,
    scale_typography_for_job_height,
)
from pixfabrica_core.theme.typography import FontPalette


def test_preview_dimensions_caps_landscape() -> None:
    pw, ph = preview_dimensions(1920, 1080)
    assert pw == MAX_PREVIEW_LONG_SIDE
    assert ph == int(1080 * MAX_PREVIEW_LONG_SIDE / 1920)


def test_preview_dimensions_caps_portrait() -> None:
    pw, ph = preview_dimensions(1080, 1920)
    assert pw == int(1080 * MAX_PREVIEW_LONG_SIDE / 1920)
    assert ph == MAX_PREVIEW_LONG_SIDE


def test_preview_dimensions_no_upscale() -> None:
    assert preview_dimensions(320, 240) == (320, 240)


def test_preview_dimensions_preserves_aspect_ratio() -> None:
    job_w, job_h = 1920, 1080
    pw, ph = preview_dimensions(job_w, job_h)
    assert abs((pw / ph) - (job_w / job_h)) < 0.02


def test_preview_dimensions_custom_cap() -> None:
    pw, ph = preview_dimensions(1920, 1080, max_long_side=480)
    assert pw == 480
    assert ph == 270


def test_scale_typography_for_job_height_matches_render_job() -> None:
    base = FontPalette()
    before = base.body_medium.size
    scaled = scale_typography_for_job_height(base, job_height=720, reference_height=1080)
    assert scaled.body_medium.size == before * (720 / 1080)


def test_scale_typography_identity_at_reference_height() -> None:
    base = FontPalette()
    scaled = scale_typography_for_job_height(base, job_height=1080, reference_height=1080)
    assert scaled.body_medium.size == base.body_medium.size


def test_job_info_scale_output_px() -> None:
    from pixfabrica_core.clips import JobInfo
    from pixfabrica_core.theme.color import ColorPalette

    export = JobInfo(
        title="t",
        description="d",
        width=1920,
        height=1080,
        fps=30.0,
        duration=8.0,
        colors=ColorPalette(),
        typography=FontPalette(),
        locale="en",
        output_width=1920,
        output_height=1080,
    )
    preview = JobInfo(
        title="t",
        description="d",
        width=480,
        height=270,
        fps=30.0,
        duration=8.0,
        colors=ColorPalette(),
        typography=FontPalette(),
        locale="en",
        output_width=1920,
        output_height=1080,
    )
    assert export.scale_output_px(100.0) == 100.0
    assert preview.scale_output_px(100.0) == 25.0
    assert export.design_height == 1080
    assert preview.design_height == 1080
