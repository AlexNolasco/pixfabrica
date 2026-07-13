"""Tests for std-image layout and upload policy."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image as PILImage

from pixfabrica_core.clips import JobInfo, PrepareContext, RenderContext, TimeState
from pixfabrica_core.file_upload_policy import DisplayWidthFactorPolicy, UploadPolicyContext
from pixfabrica_core.graphics import Rect
from pixfabrica_std.image.image import Image
from pixfabrica_std.image.image_layout import compute_image_draw_rect


def _bounds() -> Rect:
    return Rect(0, 0, 1000, 500)


def test_compute_image_draw_rect_centered() -> None:
    x, y, draw_w, draw_h = compute_image_draw_rect(
        _bounds(),
        width_frac=0.5,
        src_w=800.0,
        src_h=400.0,
        offset_x=0.5,
        offset_y=0.5,
        align="center",
    )
    assert draw_w == pytest.approx(500.0)
    assert draw_h == pytest.approx(250.0)
    assert x == pytest.approx(250.0)
    assert y == pytest.approx(125.0)


def test_compute_image_draw_rect_top_leading() -> None:
    x, y, draw_w, draw_h = compute_image_draw_rect(
        _bounds(),
        width_frac=0.2,
        src_w=100.0,
        src_h=200.0,
        offset_x=0.0,
        offset_y=0.0,
        align="topLeading",
    )
    assert draw_w == pytest.approx(200.0)
    assert draw_h == pytest.approx(400.0)
    assert x == pytest.approx(0.0)
    assert y == pytest.approx(0.0)


def test_image_declares_display_width_upload_policy() -> None:
    policy = Image.source_upload_policy()
    assert isinstance(policy, DisplayWidthFactorPolicy)
    assert policy.factor == 2.0
    assert policy.min_px == 64


def test_display_width_factor_policy_scales_with_width_param() -> None:
    policy = DisplayWidthFactorPolicy(factor=2.0, min_px=64, default_width=0.5)
    ctx = UploadPolicyContext(
        clip_type="std-image",
        plugin_id="pixfabrica-std",
        field="source",
        kind="image",
        target_width=1920,
        target_height=1080,
        clip_params={"width": 0.25},
    )
    # 0.25 × 1920 = 480 display width → 960 cap
    assert policy.max_px(ctx) == 960


def test_display_width_factor_policy_enforces_floor() -> None:
    policy = DisplayWidthFactorPolicy(factor=2.0, min_px=64, default_width=0.01)
    ctx = UploadPolicyContext(
        clip_type="std-image",
        plugin_id="pixfabrica-std",
        field="source",
        kind="image",
        target_width=100,
        target_height=100,
        clip_params={"width": 0.01},
    )
    assert policy.max_px(ctx) == 64


def test_image_source_max_px_uses_instance_width() -> None:
    clip = Image(id="img", width=0.25)
    assert clip.source_max_px(_bounds()) == 500  # 0.25 × 1000 × 2.0


def test_image_prepare_downsamples_large_source(tmp_path: Path) -> None:
    from pixfabrica_core.clips import JobInfo, PrepareContext
    from pixfabrica_core.theme.color import ColorPalette
    from pixfabrica_core.theme.typography import FontPalette

    src = tmp_path / "logo.png"
    PILImage.new("RGBA", (2000, 1000), color=(255, 0, 0, 255)).save(src)

    job = JobInfo(
        title="t",
        description="d",
        width=1000,
        height=500,
        fps=30.0,
        duration=1.0,
        colors=ColorPalette(),
        typography=FontPalette(),
        locale="en",
    )
    ctx = PrepareContext(job=job, temp_dir=tmp_path, cache_dir=tmp_path / "cache")
    clip = Image(id="img", source=str(src), width=0.5)

    clip._prepare_sync(ctx, _bounds())

    assert clip._image is not None
    assert max(clip._image.width(), clip._image.height()) <= clip.source_max_px(_bounds())


def test_image_shadow_intensity_defaults_off() -> None:
    clip = Image(id="img")
    assert clip.shadow_intensity == 0.0


def test_image_corner_radius_defaults_square() -> None:
    clip = Image(id="img")
    assert clip.corner_radius == 0.0


def test_image_draw_clips_rounded_corners(tmp_path: Path) -> None:
    from unittest.mock import MagicMock

    from pixfabrica_core.theme.color import ColorPalette
    from pixfabrica_core.theme.typography import FontPalette

    src = tmp_path / "logo.png"
    PILImage.new("RGBA", (120, 80), color=(255, 0, 0, 200)).save(src)

    job = JobInfo(
        title="t",
        description="d",
        width=1000,
        height=500,
        fps=30.0,
        duration=1.0,
        colors=ColorPalette(),
        typography=FontPalette(),
        locale="en",
    )
    ctx = PrepareContext(job=job, temp_dir=tmp_path, cache_dir=tmp_path / "cache")
    clip = Image(id="img", source=str(src), width=0.5, corner_radius=0.12)
    clip._prepare_sync(ctx, _bounds())

    canvas = MagicMock()
    draw_ctx = RenderContext(
        job=job,
        time=TimeState(t=0.0, frame=0),
        bounds=_bounds(),
        canvas=canvas,
    )
    clip.draw(draw_ctx)

    assert canvas.clipRRect.called


def test_image_prepare_bakes_alpha_shadow_when_enabled(tmp_path: Path) -> None:
    from pixfabrica_core.theme.color import ColorPalette
    from pixfabrica_core.theme.typography import FontPalette

    src = tmp_path / "logo.png"
    PILImage.new("RGBA", (120, 80), color=(255, 0, 0, 200)).save(src)

    job = JobInfo(
        title="t",
        description="d",
        width=1000,
        height=500,
        fps=30.0,
        duration=1.0,
        colors=ColorPalette(),
        typography=FontPalette(),
        locale="en",
    )
    ctx = PrepareContext(job=job, temp_dir=tmp_path, cache_dir=tmp_path / "cache")
    clip = Image(id="img", source=str(src), width=0.5, shadow_intensity=1.0)

    clip._prepare_sync(ctx, _bounds())

    assert clip._image is not None
    assert clip._shadow_image is not None
    assert clip._shadow_pad > 0.0
    assert clip._shadow_image.width() > clip._image.width()
    assert clip._shadow_image.height() > clip._image.height()


def test_image_prepare_skips_shadow_when_intensity_zero(tmp_path: Path) -> None:
    from pixfabrica_core.theme.color import ColorPalette
    from pixfabrica_core.theme.typography import FontPalette

    src = tmp_path / "logo.png"
    PILImage.new("RGBA", (120, 80), color=(255, 0, 0, 200)).save(src)

    job = JobInfo(
        title="t",
        description="d",
        width=1000,
        height=500,
        fps=30.0,
        duration=1.0,
        colors=ColorPalette(),
        typography=FontPalette(),
        locale="en",
    )
    ctx = PrepareContext(job=job, temp_dir=tmp_path, cache_dir=tmp_path / "cache")
    clip = Image(id="img", source=str(src), width=0.5, shadow_intensity=0.0)

    clip._prepare_sync(ctx, _bounds())

    assert clip._image is not None
    assert clip._shadow_image is None


def test_image_draw_stamps_shadow_before_image(tmp_path: Path) -> None:
    from unittest.mock import MagicMock

    from pixfabrica_core.theme.color import ColorPalette
    from pixfabrica_core.theme.typography import FontPalette

    src = tmp_path / "logo.png"
    PILImage.new("RGBA", (120, 80), color=(255, 0, 0, 200)).save(src)

    job = JobInfo(
        title="t",
        description="d",
        width=1000,
        height=500,
        fps=30.0,
        duration=1.0,
        colors=ColorPalette(),
        typography=FontPalette(),
        locale="en",
    )

    ctx = PrepareContext(job=job, temp_dir=tmp_path, cache_dir=tmp_path / "cache")
    clip = Image(id="img", source=str(src), width=0.5, shadow_intensity=1.0, opacity=0.5)
    clip._prepare_sync(ctx, _bounds())

    canvas = MagicMock()
    draw_ctx = RenderContext(
        job=job,
        time=TimeState(t=0.0, frame=0),
        bounds=_bounds(),
        canvas=canvas,
    )
    clip.draw(draw_ctx)

    assert canvas.drawImageRect.call_count == 2
    assert canvas.saveLayer.called
