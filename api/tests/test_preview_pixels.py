import skia

from pixfabrica_api.preview_runtime import typography_for_preview_surface
from pixfabrica_api.routes.preview import _skia_surface_rgba_bytes
from pixfabrica_core.theme.typography import FontPalette, FontSpec


def test_skia_surface_rgba_bytes_swaps_bgra_channels() -> None:
    surface = skia.Surface(1, 1)
    canvas = surface.getCanvas()
    canvas.clear(skia.ColorTRANSPARENT)
    # Opaque red in BGRA layout: B=0, G=0, R=255, A=255
    canvas.drawColor(skia.ColorRED)

    rgba = _skia_surface_rgba_bytes(surface)
    assert len(rgba) == 4
    assert rgba[0] == 255  # R
    assert rgba[1] == 0  # G
    assert rgba[2] == 0  # B
    assert rgba[3] == 255  # A


def test_typography_for_preview_surface_scales_live_preview_only() -> None:
    base = FontPalette(
        body_medium=FontSpec(family="Inter", weight=500, size=30.0),
    )
    live = typography_for_preview_surface(
        base,
        job_height=1080,
        preview_height=360,
        scale_to_preview=True,
    )
    full_res = typography_for_preview_surface(
        base,
        job_height=1080,
        preview_height=360,
        scale_to_preview=False,
    )
    assert abs(live.body_medium.size - 10.0) < 0.01
    assert abs(full_res.body_medium.size - 30.0) < 0.01
