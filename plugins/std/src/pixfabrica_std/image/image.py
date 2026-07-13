from __future__ import annotations

import logging
import math
from typing import ClassVar

import numpy as np
import skia
from PIL import Image as PILImage
from pydantic import Field, PrivateAttr

from pixfabrica_core.clips import ClipCategory, ClipSkia, PrepareContext, RenderContext
from pixfabrica_core.file_upload_policy import DisplayWidthFactorPolicy, manifest_covers_max_px
from pixfabrica_core.graphics import Rect
from pixfabrica_core.prepare_diagnostics import record_prepare_asset_failure
from pixfabrica_core.ui_schema import (
    stock_attribution_field,
    stock_image_field,
    stock_provider_field,
)
from pixfabrica_std.image.image_layout import ImageAlign, compute_image_draw_rect
from pixfabrica_std.media_source import resolve_local_source_path
from pixfabrica_std.tilt import ANGLE_FULL_DESC, ANGLE_FULL_MAX, ANGLE_FULL_MIN

log = logging.getLogger("pixfabrica.std.Image")

# Cap long edge at factor × displayed width (width_frac × bounds.width). Upload (API)
# and prepare (CLI safety net) both use this via source_upload_policy().
_DISPLAY_WIDTH_FACTOR = 2.0
_MIN_UPLOAD_PX = 64


def _bake_alpha_drop_shadow(
    image: skia.Image,
    *,
    intensity: float,
) -> tuple[skia.Image, float] | None:
    """Bake an even alpha-following soft shadow; returns (image, pad_px in source space)."""
    if intensity <= 0.0:
        return None

    src_w = float(image.width())
    src_h = float(image.height())
    if src_w <= 0.0 or src_h <= 0.0:
        return None

    ref = max(src_w, src_h)
    sigma = max(2.0, ref * 0.052)
    alpha = max(0, min(255, int(round(78 * intensity))))

    spread = sigma * 3.0
    pad = float(math.ceil(spread) + 2)
    side_w = int(math.ceil(src_w + pad * 2.0))
    side_h = int(math.ceil(src_h + pad * 2.0))

    surface = skia.Surface(side_w, side_h)
    canvas = surface.getCanvas()
    canvas.clear(skia.ColorTRANSPARENT)
    paint = skia.Paint(AntiAlias=True)
    paint.setImageFilter(
        skia.ImageFilters.DropShadowOnly(0.0, 0.0, sigma, sigma, skia.ColorSetARGB(alpha, 0, 0, 0))
    )
    canvas.drawImage(image, pad, pad, skia.SamplingOptions(), paint)
    return surface.makeImageSnapshot(), pad


def _corner_radius_px(width: float, height: float, corner_radius: float) -> float:
    if corner_radius <= 0.0 or width <= 0.0 or height <= 0.0:
        return 0.0
    return corner_radius * min(width, height)


def _rounded_image_mask(image: skia.Image, corner_radius: float) -> skia.Image:
    """Return ``image`` clipped to a rounded rect in source pixel space."""
    if corner_radius <= 0.0:
        return image

    src_w = float(image.width())
    src_h = float(image.height())
    radius = _corner_radius_px(src_w, src_h, corner_radius)
    if radius <= 0.0:
        return image

    surface = skia.Surface(int(src_w), int(src_h))
    canvas = surface.getCanvas()
    canvas.clear(skia.ColorTRANSPARENT)
    rounded = skia.RRect()
    rounded.setRectXY(skia.Rect.MakeWH(src_w, src_h), radius, radius)
    canvas.clipRRect(rounded, skia.ClipOp.kIntersect, True)
    canvas.drawImage(image, 0.0, 0.0, skia.SamplingOptions())
    return surface.makeImageSnapshot()


class Image(ClipSkia):
    """Static raster image placed within clip bounds with optional rotation."""

    clip_type: ClassVar[str] = "std-image"
    clip_category: ClassVar[ClipCategory] = ClipCategory.IMAGE
    clip_tags: ClassVar[list[str]] = []

    source: str | None = stock_image_field(
        default=None,
        description="Local file path to a prepared image",
    )
    offset_x: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Horizontal bounds anchor as fraction of clip width (0=left, 1=right)",
    )
    offset_y: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Vertical bounds anchor as fraction of clip height (0=top, 1=bottom)",
    )
    width: float = Field(
        default=0.5,
        ge=0.01,
        le=1.0,
        multiple_of=0.01,
        description="Drawn width as a fraction of clip bounds width; height follows aspect ratio",
    )
    angle: float = Field(
        default=0.0,
        ge=ANGLE_FULL_MIN,
        le=ANGLE_FULL_MAX,
        multiple_of=1.0,
        description=ANGLE_FULL_DESC,
    )
    opacity: float = Field(
        default=1.0, ge=0.0, le=1.0, multiple_of=0.1, description="Overall layer opacity"
    )
    align: ImageAlign = Field(
        default="center",
        description="Which point on the image attaches to the offset anchor",
    )
    shadow_intensity: float = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
        multiple_of=0.1,
        description="Soft shadow strength (0=off, 1=default, 2=heavy); even glow around image alpha",
    )
    corner_radius: float = Field(
        default=0.0,
        ge=0.0,
        le=0.5,
        multiple_of=0.01,
        description="Corner radius as fraction of the shorter image side (0 = square corners)",
    )
    source_attribution: str = stock_attribution_field("source")
    source_provider: str = stock_provider_field("source")

    _image: skia.Image | None = PrivateAttr(default=None)
    _shadow_image: skia.Image | None = PrivateAttr(default=None)
    _shadow_pad: float = PrivateAttr(default=0.0)

    @classmethod
    def source_upload_policy(cls) -> DisplayWidthFactorPolicy:
        return DisplayWidthFactorPolicy(
            factor=_DISPLAY_WIDTH_FACTOR,
            min_px=_MIN_UPLOAD_PX,
            default_width=0.5,
        )

    def source_max_px(self, bounds: Rect) -> int:
        return self.source_upload_policy().max_px_from_bounds(
            bounds.width,
            bounds.height,
            width_frac=self.width,
        )

    async def prepare(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        import asyncio

        await asyncio.to_thread(self._prepare_sync, ctx, bounds)

    def _prepare_sync(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        if not self.source:
            return
        try:
            local_path = resolve_local_source_path(self.source)
        except Exception as exc:
            record_prepare_asset_failure(
                ctx,
                kind="clip",
                ref_id=self.id,
                clip_type=self.clip_type,
                field="source",
                source=self.source,
                exc=exc,
            )
            log.warning("Image %s: could not resolve source %r — %s", self.id, self.source, exc)
            return

        if not local_path.is_file():
            record_prepare_asset_failure(
                ctx,
                kind="clip",
                ref_id=self.id,
                clip_type=self.clip_type,
                field="source",
                source=self.source,
                exc=FileNotFoundError(local_path),
                code="not_found",
            )
            log.warning("Image %s: source file not found %r", self.id, local_path)
            return

        try:
            pil_img = PILImage.open(str(local_path)).convert("RGBA")
        except Exception as exc:
            record_prepare_asset_failure(
                ctx,
                kind="clip",
                ref_id=self.id,
                clip_type=self.clip_type,
                field="source",
                source=self.source,
                exc=exc,
                code="load_failed",
            )
            log.warning("Image %s: failed to load image %r — %s", self.id, local_path, exc)
            return

        b = bounds or Rect(0, 0, ctx.job.width, ctx.job.height)
        max_dim = self.source_max_px(b)

        if (
            not manifest_covers_max_px(local_path, max_dim)
            and max(pil_img.width, pil_img.height) > max_dim
        ):
            pil_img.thumbnail((max_dim, max_dim), PILImage.Resampling.LANCZOS)
            log.debug("Image %s: downsampled to %dx%d", self.id, pil_img.width, pil_img.height)

        self._image = skia.Image.fromarray(
            np.array(pil_img),
            colorType=skia.ColorType.kRGBA_8888_ColorType,
        )
        self._shadow_image = None
        self._shadow_pad = 0.0
        shadow_source = _rounded_image_mask(self._image, float(self.corner_radius))
        baked = _bake_alpha_drop_shadow(shadow_source, intensity=float(self.shadow_intensity))
        if baked is not None:
            self._shadow_image, self._shadow_pad = baked

    def draw(self, ctx: RenderContext) -> None:
        if self._image is None:
            return

        canvas: skia.Canvas = ctx.canvas
        bnd = ctx.bounds
        src_w = float(self._image.width())
        src_h = float(self._image.height())

        x, y, draw_w, draw_h = compute_image_draw_rect(
            bnd,
            width_frac=self.width,
            src_w=src_w,
            src_h=src_h,
            offset_x=self.offset_x,
            offset_y=self.offset_y,
            align=self.align,
        )
        if draw_w <= 0 or draw_h <= 0:
            return

        cx = x + draw_w / 2.0
        cy = y + draw_h / 2.0
        bounds_rect = skia.Rect.MakeXYWH(bnd.x, bnd.y, float(bnd.width), float(bnd.height))
        layer_active = self.opacity < 1.0

        canvas.save()
        canvas.clipRect(bounds_rect)
        if layer_active:
            layer_paint = skia.Paint()
            layer_paint.setAlphaf(self.opacity)
            canvas.saveLayer(bounds_rect, layer_paint)

        canvas.translate(cx, cy)
        if self.angle:
            canvas.rotate(self.angle)
        canvas.translate(-draw_w / 2.0, -draw_h / 2.0)

        scale = draw_w / src_w
        if self._shadow_image is not None and self._shadow_pad > 0.0:
            pad = self._shadow_pad * scale
            shadow_w = float(self._shadow_image.width()) * scale
            shadow_h = float(self._shadow_image.height()) * scale
            canvas.drawImageRect(
                self._shadow_image,
                skia.Rect.MakeWH(
                    float(self._shadow_image.width()), float(self._shadow_image.height())
                ),
                skia.Rect.MakeXYWH(-pad, -pad, shadow_w, shadow_h),
                skia.SamplingOptions(skia.FilterMode.kLinear),
            )

        radius_px = _corner_radius_px(draw_w, draw_h, float(self.corner_radius))
        if radius_px > 0.0:
            rounded = skia.RRect()
            rounded.setRectXY(skia.Rect.MakeWH(draw_w, draw_h), radius_px, radius_px)
            canvas.save()
            canvas.clipRRect(rounded, skia.ClipOp.kIntersect, True)

        image_paint = skia.Paint()
        canvas.drawImageRect(
            self._image,
            skia.Rect.MakeWH(src_w, src_h),
            skia.Rect.MakeWH(draw_w, draw_h),
            skia.SamplingOptions(skia.FilterMode.kLinear),
            image_paint,
        )

        if radius_px > 0.0:
            canvas.restore()

        if layer_active:
            canvas.restore()
        canvas.restore()
