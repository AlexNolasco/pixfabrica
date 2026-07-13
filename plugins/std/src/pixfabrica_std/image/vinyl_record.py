from __future__ import annotations

import asyncio
import logging
import math
from typing import ClassVar, Literal

import numpy as np
import skia
from PIL import Image as PILImage
from pydantic import Field, PrivateAttr

from pixfabrica_core.clips import ClipCategory, ClipSkia, PrepareContext, RenderContext
from pixfabrica_core.file_upload_policy import VinylCoverFactorPolicy, manifest_covers_max_px
from pixfabrica_core.graphics import Rect
from pixfabrica_core.prepare_diagnostics import record_prepare_asset_failure
from pixfabrica_core.theme.color import Color, ColorToken, color_field, resolve_color
from pixfabrica_std.common import FitMode
from pixfabrica_std.media_source import resolve_local_source_path
from pixfabrica_std.tilt import ANGLE_FULL_DESC, ANGLE_FULL_MAX, ANGLE_FULL_MIN

log = logging.getLogger("pixfabrica.std.vinyl_record")

# Cover art cap: factor × disc diameter (disc itself capped at _DISC_BAKE_MAX_PX).
# Upload (API) and prepare (CLI safety net) both use source_upload_policy().
_MAX_DIM_FACTOR = 1.2

# Transparent border around the baked disc so rotation antialiasing has clean room.
_DISC_BAKE_PAD_PX = 4

# Cap the baked disc image size — anything larger is wasted resampling work per frame
# (the disc rotates every frame on the CPU). 768 keeps grooves crisp at 1080 output and
# is invisible at 720.
_DISC_BAKE_MAX_PX = 768

# LP sleeve is static — bake the fitted cover once; cap size so huge frames stay cheap.
_SLEEVE_BAKE_MAX_PX = 768


def _layout_rect(bounds: Rect, width: float) -> Rect:
    """Layout region: ``width`` fraction of bounds width (centered), full bounds height."""
    wf = max(0.0, min(1.0, float(width)))
    iw = bounds.width * wf
    ih = bounds.height
    ix = bounds.x + (bounds.width - iw) * 0.5
    iy = bounds.y
    return Rect(ix, iy, iw, ih)


class VinylRecord(ClipSkia):
    """Spinning vinyl record with optional cover art.

    LP mode lays a square sleeve on the left and a disc emerging from the right.
    `disc_scale` scales disc diameter vs sleeve side in LP + image mode. The disc overlaps the sleeve
    by `disc_overlap` (fraction of the disc) so the sleeve appears to hold the record.
    `width` sets layout width as a fraction of bounds (centered horizontally); full
    bounds height is used. CENTERED mode renders a single disc and circle-clips the
    cover into the label area, framed by a label_color ring. LP mode with cover art
    uses the same circle-clipped label on the spinning disc (sleeve shows the jacket
    separately). With no source, both modes degrade to a solid label_color center.
    Groove specular is baked so it spins with the disc (clear rotation cue);
    soft drop shadows sit under the sleeve and disc and respect `shadow_intensity`.
    The LP sleeve (fill + fitted cover) is pre-baked in `prepare()` so each frame only
    scales and blits it. The disc spins at `rpm`; the sleeve in LP mode is static.
    `rpm=0` skips disc rotation for a fast axis-aligned blit. `angle` tilts the
    whole clip area as a unit.
    """

    clip_type: ClassVar[str] = "std-vinyl-record"
    clip_category: ClassVar[ClipCategory] = ClipCategory.IMAGE
    clip_tags: ClassVar[list[str]] = []

    source: str | None = Field(
        default=None,
        description="Cover art: local file path to a prepared image. Optional — disc renders solo when empty.",
    )
    display_mode: Literal["lp", "centered"] = Field(
        default="lp",
        description="'lp' = sleeve + disc side-by-side; 'centered' = single disc with image as the label",
    )
    fit: FitMode = Field(
        default=FitMode.COVER,
        description="How the cover art fills the sleeve square (LP + image only). COVER crops to a full square; CONTAIN / FIT_WIDTH / FIT_HEIGHT center the bitmap and leave bands — use sleeve_fill so the jacket still reads as a square.",
    )
    sleeve_fill: ColorToken | Color = color_field(
        ColorToken.BACKGROUND,
        description="LP + image: solid color behind the cover inside the square sleeve (visible when fit does not fill the square, e.g. CONTAIN)",
    )
    label_color: ColorToken | Color = color_field(
        ColorToken.PRIMARY,
        description="Solid center label when no cover art; ring framing the circle-clipped label when source is set (LP or centered)",
    )
    vinyl_color: ColorToken | Color = color_field(
        ColorToken.NEUTRAL,
        default=Color("#15151A"),
        description="Vinyl disc body color; defaults to a near-black so themes don't accidentally tint the record",
    )
    label_ring_width: float = Field(
        default=0.08,
        ge=0.0,
        le=0.45,
        multiple_of=0.01,
        description="Thickness of the label_color ring framing the circle-clipped cover on the disc (LP or centered + source), as a fraction of the disc radius",
    )
    disc_overlap: float = Field(
        default=0.35,
        ge=0.0,
        le=0.7,
        multiple_of=0.1,
        description="LP mode + image only: fraction of the disc covered by the sleeve (0=no overlap, 0.5=half, 0.7=mostly hidden)",
    )
    disc_scale: float = Field(
        default=0.95,
        ge=0.85,
        le=1.55,
        multiple_of=0.01,
        description="LP mode + image only: disc diameter as a multiple of the sleeve side (1=equal; >1 fixes the circle looking smaller than the square)",
    )
    label_radius_fraction: float = Field(
        default=0.33,
        ge=0.12,
        le=0.55,
        multiple_of=0.01,
        description="Outer label radius as a fraction of the disc radius (0.5 = label diameter equals disc radius)",
    )
    rpm: float = Field(
        default=33.3,
        ge=0.0,
        le=50.0,
        multiple_of=1.0,
        description="Disc rotation speed in revolutions per minute (0=static, 33.3=standard LP, 45, 78 also realistic). 0 enables a fast axis-aligned draw path.",
    )
    direction: Literal["cw", "ccw"] = Field(
        default="cw",
        description="Disc rotation direction; 'cw' = clockwise viewed from above (real LP convention)",
    )
    offset_x: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Horizontal centroid of the clip area as fraction of bounds width (0=left, 0.5=center, 1=right)",
    )
    offset_y: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Vertical centroid of the clip area as fraction of bounds height (0=top, 0.5=center, 1=bottom)",
    )
    width: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Layout width as a fraction of clip bounds (1.0 = full horizontal span); uses full clip height",
    )
    angle: float = Field(
        default=0.0,
        ge=ANGLE_FULL_MIN,
        le=ANGLE_FULL_MAX,
        multiple_of=1.0,
        description=ANGLE_FULL_DESC,
    )
    opacity: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        multiple_of=0.1,
        description="Overall layer opacity",
    )
    shadow_intensity: float = Field(
        default=1.0,
        ge=0.0,
        le=2.0,
        multiple_of=0.1,
        description="Strength of drop shadows under the disc and sleeve (0=off, 1=default, 2=heavy)",
    )

    _cover_image: skia.Image | None = PrivateAttr(default=None)
    _disc_image: skia.Image | None = PrivateAttr(default=None)
    _disc_diameter_px: float = PrivateAttr(default=0.0)
    _disc_bake_side_px: float = PrivateAttr(default=0.0)
    _disc_shadow_image: skia.Image | None = PrivateAttr(default=None)
    _disc_shadow_offset_px: float = PrivateAttr(default=0.0)
    _sleeve_shadow_image: skia.Image | None = PrivateAttr(default=None)
    _sleeve_shadow_offset_px: float = PrivateAttr(default=0.0)
    _shadow_disc_diameter_px: float = PrivateAttr(default=0.0)
    _shadow_sleeve_side_px: float = PrivateAttr(default=0.0)
    _prepare_key: tuple | None = PrivateAttr(default=None)
    _sleeve_tile_image: skia.Image | None = PrivateAttr(default=None)
    _sleeve_bake_side_px: float = PrivateAttr(default=0.0)

    @classmethod
    def source_upload_policy(cls) -> VinylCoverFactorPolicy:
        return VinylCoverFactorPolicy(factor=_MAX_DIM_FACTOR, disc_bake_max_px=_DISC_BAKE_MAX_PX)

    @classmethod
    def source_cover_max_px(
        cls,
        bounds: Rect,
        *,
        width: float,
    ) -> int:
        return cls.source_upload_policy().cover_max_px(
            bounds.width,
            bounds.height,
            width_frac=width,
        )

    def _layout(self, lb: Rect) -> tuple[float, float, float, float]:
        """Return (disc_diameter, sleeve_side, sleeve_center_dx, disc_center_dx)
        for the current clip settings inside content rect ``lb``. Same math used by
        prepare() (for shadow baking) and draw() (for placement)."""
        has_image = self._cover_image is not None
        if self.display_mode == "lp" and has_image:
            ov = self.disc_overlap
            sc = self.disc_scale
            w, h = float(lb.width), float(lb.height)
            denom_w = 1.0 + sc * (1.0 - ov)
            denom_h = max(1.0, sc)
            sleeve_side = float(min(w / denom_w, h / denom_h))
            disc_diameter = sleeve_side * sc
            half_offset = (sleeve_side / 2.0 + disc_diameter / 2.0 - ov * disc_diameter) / 2.0
            sleeve_center_dx = -half_offset
            disc_center_dx = +half_offset
            bbox_left = min(
                sleeve_center_dx - sleeve_side / 2.0, disc_center_dx - disc_diameter / 2.0
            )
            bbox_right = max(
                sleeve_center_dx + sleeve_side / 2.0, disc_center_dx + disc_diameter / 2.0
            )
            recenter_x = -(bbox_left + bbox_right) / 2.0
            sleeve_center_dx += recenter_x
            disc_center_dx += recenter_x
            return disc_diameter, sleeve_side, sleeve_center_dx, disc_center_dx

        disc_diameter = float(min(lb.width, lb.height))
        return disc_diameter, disc_diameter, 0.0, 0.0

    async def prepare(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        await asyncio.to_thread(self._prepare_sync, ctx, bounds)

    def _prepare_sync(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        if self.width <= 0.0:
            self._prepare_key = None
            self._cover_image = None
            self._disc_image = None
            return

        b = bounds or Rect(0, 0, ctx.job.width, ctx.job.height)
        lb = _layout_rect(b, self.width)
        # Bake at the largest size the disc might be drawn at (single-disc layout),
        # but cap so the per-frame rotation+resample stays cheap. Quality loss above
        # the cap is invisible because grooves are subtle.
        full_disc_diameter_px = float(min(lb.width, lb.height))
        disc_diameter_px = min(full_disc_diameter_px, float(_DISC_BAKE_MAX_PX))

        resolved_label = resolve_color(self.label_color, ctx.job.colors)
        resolved_vinyl = resolve_color(self.vinyl_color, ctx.job.colors)
        resolved_sleeve_fill = resolve_color(self.sleeve_fill, ctx.job.colors)

        # Layout sizes for shadow baking — must match _layout() in draw().
        will_have_image = bool(self.source)
        if self.display_mode == "lp" and will_have_image:
            ov = self.disc_overlap
            sc = self.disc_scale
            denom_w = 1.0 + sc * (1.0 - ov)
            denom_h = max(1.0, sc)
            sleeve_side_layout = float(min(lb.width / denom_w, lb.height / denom_h))
            disc_diameter_layout = sleeve_side_layout * sc
        else:
            disc_diameter_layout = full_disc_diameter_px
            sleeve_side_layout = full_disc_diameter_px

        key = (
            self.source,
            self.display_mode,
            str(self.fit),
            resolved_label.hex,
            resolved_vinyl.hex,
            resolved_sleeve_fill.hex,
            round(self.label_ring_width, 4),
            round(self.label_radius_fraction, 4),
            round(self.width, 4),
            round(self.disc_overlap, 4),
            round(self.disc_scale, 4),
            round(self.shadow_intensity, 4),
            round(disc_diameter_px),
            round(lb.width),
            round(lb.height),
        )
        if key == self._prepare_key:
            return

        # Load cover art if a source is provided. Failure → fall back to disc-only.
        if self.source:
            try:
                local_path = resolve_local_source_path(self.source)
                if not local_path.is_file():
                    raise FileNotFoundError(local_path)
                pil_img = PILImage.open(str(local_path)).convert("RGBA")
                max_dim = self.source_cover_max_px(
                    b,
                    width=self.width,
                )
                if (
                    not manifest_covers_max_px(local_path, max_dim)
                    and max(pil_img.width, pil_img.height) > max_dim
                ):
                    pil_img.thumbnail((max_dim, max_dim), PILImage.Resampling.LANCZOS)
                    log.debug(
                        "VinylRecord %s: downsampled cover to %dx%d",
                        self.id,
                        pil_img.width,
                        pil_img.height,
                    )
                self._cover_image = skia.Image.fromarray(
                    np.array(pil_img),
                    colorType=skia.ColorType.kRGBA_8888_ColorType,
                )
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
                log.warning(
                    "VinylRecord %s: failed to load cover %r — %s", self.id, self.source, exc
                )
                self._cover_image = None
        else:
            self._cover_image = None

        embed_image = self._cover_image is not None
        self._disc_image, self._disc_bake_side_px = _bake_disc(
            disc_diameter_px=disc_diameter_px,
            vinyl_color=resolved_vinyl,
            label_color=resolved_label,
            label_radius_fraction=self.label_radius_fraction,
            label_ring_width=self.label_ring_width,
            cover_image=self._cover_image if embed_image else None,
            fit=self.fit,
        )
        self._disc_diameter_px = disc_diameter_px

        self._sleeve_tile_image = None
        self._sleeve_bake_side_px = 0.0
        if self.display_mode == "lp" and self._cover_image is not None:
            bake_side = float(min(sleeve_side_layout, float(_SLEEVE_BAKE_MAX_PX)))
            side_i = max(1, int(math.ceil(bake_side)))
            surf = skia.Surface(side_i, side_i)
            sc = surf.getCanvas()
            sr, sg, sb, sa = resolved_sleeve_fill.rgba
            fill_paint = skia.Paint(AntiAlias=True)
            fill_paint.setColor4f(skia.Color4f(sr, sg, sb, sa))
            sc.drawRect(skia.Rect.MakeWH(float(side_i), float(side_i)), fill_paint)
            tile_rect = Rect(0.0, 0.0, float(side_i), float(side_i))
            img_paint = skia.Paint(AntiAlias=True)
            _draw_fitted(sc, tile_rect, self._cover_image, self.fit, img_paint)
            self._sleeve_tile_image = surf.makeImageSnapshot()
            self._sleeve_bake_side_px = float(side_i)

        # Pre-bake drop shadows once so the per-frame cost is a single drawImage
        # instead of a CPU gaussian blur. They scale at draw time alongside the
        # disc/sleeve, so live bounds changes still look right.
        shadow_intensity = max(0.0, float(self.shadow_intensity))
        self._disc_shadow_image = None
        self._sleeve_shadow_image = None
        if shadow_intensity > 0.0:
            self._shadow_disc_diameter_px = disc_diameter_layout
            self._shadow_sleeve_side_px = sleeve_side_layout

            ddx = disc_diameter_layout * 0.022
            ddy = disc_diameter_layout * 0.036
            dsigma = max(2.0, disc_diameter_layout * 0.052)
            disc_alpha = max(0, min(255, int(round(78 * shadow_intensity))))
            self._disc_shadow_image, self._disc_shadow_offset_px = _bake_circle_shadow(
                disc_diameter_layout / 2.0, ddx, ddy, dsigma, disc_alpha
            )

            if self.display_mode == "lp" and self._cover_image is not None:
                sdx = sleeve_side_layout * 0.016
                sdy = sleeve_side_layout * 0.028
                ssigma = max(2.0, sleeve_side_layout * 0.042)
                sleeve_alpha = max(0, min(255, int(round(72 * shadow_intensity))))
                self._sleeve_shadow_image, self._sleeve_shadow_offset_px = _bake_square_shadow(
                    sleeve_side_layout, sdx, sdy, ssigma, sleeve_alpha
                )

        self._prepare_key = key

    def draw(self, ctx: RenderContext) -> None:
        if self._disc_image is None or self.width <= 0.0:
            return

        canvas: skia.Canvas = ctx.canvas
        b = ctx.bounds
        lb = _layout_rect(b, self.width)

        has_image = self._cover_image is not None
        is_lp_with_image = self.display_mode == "lp" and has_image

        disc_diameter, sleeve_side, sleeve_center_dx, disc_center_dx = self._layout(lb)

        cx = b.x + self.offset_x * b.width
        cy = b.y + self.offset_y * b.height

        canvas.save()
        canvas.clipRect(skia.Rect.MakeXYWH(float(b.x), float(b.y), float(b.width), float(b.height)))

        layer_active = self.opacity < 1.0
        if layer_active:
            layer_paint = skia.Paint()
            layer_paint.setAlphaf(self.opacity)
            canvas.saveLayer(
                skia.Rect.MakeXYWH(float(b.x), float(b.y), float(b.width), float(b.height)),
                layer_paint,
            )

        canvas.translate(cx, cy)
        if self.angle != 0.0:
            canvas.rotate(self.angle)

        # Pre-baked drop shadows (bake-once, drawImage-per-frame).
        if self._disc_shadow_image is not None and self._shadow_disc_diameter_px > 0:
            shadow_scale = disc_diameter / self._shadow_disc_diameter_px
            canvas.save()
            canvas.translate(disc_center_dx, 0.0)
            canvas.scale(shadow_scale, shadow_scale)
            half = self._disc_shadow_offset_px
            canvas.drawImage(self._disc_shadow_image, -half, -half)
            canvas.restore()

        if (
            is_lp_with_image
            and self._sleeve_shadow_image is not None
            and self._shadow_sleeve_side_px > 0
        ):
            sleeve_scale = sleeve_side / self._shadow_sleeve_side_px
            canvas.save()
            canvas.translate(sleeve_center_dx, 0.0)
            canvas.scale(sleeve_scale, sleeve_scale)
            half_s = self._sleeve_shadow_offset_px
            canvas.drawImage(self._sleeve_shadow_image, -half_s, -half_s)
            canvas.restore()

        # Spinning disc (specular sweep is baked in, so it rotates with the disc).
        # rpm=0 → skip the rotate() call so Skia takes the axis-aligned blit fast path
        # (~30× faster than rotated drawImage).
        canvas.save()
        canvas.translate(disc_center_dx, 0.0)
        if self.rpm > 0.0:
            spin_sign = 1.0 if self.direction == "cw" else -1.0
            # 1 RPM = 6 degrees/second.
            spin_angle = spin_sign * self.rpm * 6.0 * ctx.time.t
            canvas.rotate(spin_angle)
        scale = disc_diameter / self._disc_diameter_px
        canvas.scale(scale, scale)
        half_bake = self._disc_bake_side_px / 2.0
        disc_paint = skia.Paint(AntiAlias=True)
        canvas.drawImage(self._disc_image, -half_bake, -half_bake, paint=disc_paint)
        canvas.restore()

        if is_lp_with_image:
            assert self._cover_image is not None
            sleeve_left = sleeve_center_dx - sleeve_side / 2.0
            sleeve_top = -sleeve_side / 2.0
            if self._sleeve_tile_image is not None and self._sleeve_bake_side_px > 0:
                canvas.save()
                canvas.translate(float(sleeve_left), float(sleeve_top))
                scl = sleeve_side / self._sleeve_bake_side_px
                canvas.scale(scl, scl)
                canvas.drawImage(
                    self._sleeve_tile_image,
                    0.0,
                    0.0,
                    paint=skia.Paint(AntiAlias=True),
                )
                canvas.restore()
            else:
                sleeve_sk = skia.Rect.MakeXYWH(
                    float(sleeve_left), float(sleeve_top), float(sleeve_side), float(sleeve_side)
                )
                canvas.save()
                canvas.clipRect(sleeve_sk, skia.ClipOp.kIntersect, doAntiAlias=True)
                sr, sg, sb, sa = resolve_color(self.sleeve_fill, ctx.job.colors).rgba
                backing = skia.Paint(AntiAlias=True)
                backing.setColor4f(skia.Color4f(sr, sg, sb, sa))
                canvas.drawRect(sleeve_sk, backing)
                sleeve_rect = Rect(sleeve_left, sleeve_top, sleeve_side, sleeve_side)
                sleeve_paint = skia.Paint(AntiAlias=True)
                _draw_fitted(canvas, sleeve_rect, self._cover_image, self.fit, sleeve_paint)
                canvas.restore()

        if layer_active:
            canvas.restore()
        canvas.restore()


def _bake_disc(
    *,
    disc_diameter_px: float,
    vinyl_color: Color,
    label_color: Color,
    label_radius_fraction: float,
    label_ring_width: float,
    cover_image: skia.Image | None,
    fit: FitMode,
) -> tuple[skia.Image, float]:
    """Bake the entire disc surface (vinyl, grooves, lead bands, vignette, baked
    specular sweep, label fill, optional inset image, label-well shadow, spindle hole)
    into a square skia.Image. Returns (image, side_px). Specular rotates with the disc.

    The disc center is placed at (side/2, side/2). A few transparent pixels of padding
    around the disc keep rotation antialiasing clean.
    """
    pad = _DISC_BAKE_PAD_PX
    side = int(math.ceil(disc_diameter_px)) + 2 * pad
    radius = disc_diameter_px / 2.0
    cx = side / 2.0
    cy = side / 2.0
    label_outer_r = radius * label_radius_fraction
    grooves_inner = radius * max(0.55, label_radius_fraction + 0.05)
    grooves_outer = radius * 0.98
    inner_lead_r = radius * (label_radius_fraction + 0.06)
    inner_lead_r = max(
        label_outer_r + max(1.0, disc_diameter_px * 0.004),
        min(inner_lead_r, grooves_inner - max(1.5, disc_diameter_px * 0.006)),
    )

    surface = skia.Surface(side, side)
    canvas = surface.getCanvas()
    canvas.clear(skia.ColorTRANSPARENT)

    vr, vg, vb, _ = vinyl_color.rgba
    lr, lg, lb, _ = label_color.rgba

    vinyl_paint = skia.Paint(AntiAlias=True)
    vinyl_paint.setColor4f(skia.Color4f(vr, vg, vb, 1.0))
    canvas.drawCircle(cx, cy, radius, vinyl_paint)

    vign_paint = skia.Paint(AntiAlias=True)
    vign_paint.setShader(
        skia.GradientShader.MakeRadial(
            center=(cx, cy),
            radius=radius,
            colors=[
                skia.Color4f(0.0, 0.0, 0.0, 0.08),
                skia.Color4f(0.0, 0.0, 0.0, 0.0),
            ],
            positions=[0.0, 1.0],
        )
    )
    canvas.drawCircle(cx, cy, radius, vign_paint)

    grooves_count = 80
    groove_paint = skia.Paint(AntiAlias=True)
    groove_paint.setStyle(skia.Paint.kStroke_Style)
    groove_paint.setStrokeWidth(max(0.7, disc_diameter_px / 500.0))
    groove_paint.setColor4f(
        skia.Color4f(
            min(1.0, vr + 0.22),
            min(1.0, vg + 0.22),
            min(1.0, vb + 0.22),
            0.35,
        )
    )
    for i in range(grooves_count):
        t = i / max(1, grooves_count - 1)
        rr = grooves_inner + t * (grooves_outer - grooves_inner)
        canvas.drawCircle(cx, cy, rr, groove_paint)

    band_paint = skia.Paint(AntiAlias=True)
    band_paint.setStyle(skia.Paint.kStroke_Style)
    band_paint.setStrokeWidth(max(1.0, disc_diameter_px * 0.010))
    band_paint.setColor4f(
        skia.Color4f(
            min(1.0, vr + 0.05),
            min(1.0, vg + 0.05),
            min(1.0, vb + 0.05),
            0.45,
        )
    )
    canvas.drawCircle(cx, cy, radius * 0.965, band_paint)
    canvas.drawCircle(cx, cy, inner_lead_r, band_paint)

    # Specular sweep — narrow ~30° lighter arc. Drawn over the full disc; the
    # opaque label drawn afterward covers any spec on the inner half. The sweep is
    # baked so it rotates with the disc, providing a clear visual rotation cue.
    spec_paint = skia.Paint(AntiAlias=True)
    spec_paint.setShader(
        skia.GradientShader.MakeSweep(
            cx=cx,
            cy=cy,
            colors=[
                skia.Color4f(1.0, 1.0, 1.0, 0.0),
                skia.Color4f(1.0, 1.0, 1.0, 0.0),
                skia.Color4f(1.0, 1.0, 1.0, 0.15),
                skia.Color4f(1.0, 1.0, 1.0, 0.0),
                skia.Color4f(1.0, 1.0, 1.0, 0.0),
            ],
            positions=[0.0, 0.20, 0.25, 0.30, 1.0],
        )
    )
    canvas.drawCircle(cx, cy, radius, spec_paint)

    label_paint = skia.Paint(AntiAlias=True)
    label_paint.setColor4f(skia.Color4f(lr, lg, lb, 1.0))
    canvas.drawCircle(cx, cy, label_outer_r, label_paint)

    well_paint = skia.Paint(AntiAlias=True)
    well_paint.setStyle(skia.Paint.kStroke_Style)
    well_paint.setStrokeWidth(max(1.0, disc_diameter_px * 0.010))
    well_paint.setColor4f(skia.Color4f(0.0, 0.0, 0.0, 0.18))
    canvas.drawCircle(cx, cy, label_outer_r, well_paint)

    if cover_image is not None:
        inner_r = max(1.0, label_outer_r - label_ring_width * radius)
        canvas.save()
        clip_path = skia.Path()
        clip_path.addCircle(cx, cy, inner_r)
        canvas.clipPath(clip_path, doAntiAlias=True)
        img_rect = Rect(cx - inner_r, cy - inner_r, 2 * inner_r, 2 * inner_r)
        cover_paint = skia.Paint(AntiAlias=True)
        # Always COVER inside the circular clip — fit doesn't translate cleanly to a circle.
        _draw_fitted(canvas, img_rect, cover_image, FitMode.COVER, cover_paint)
        canvas.restore()
        _ = fit  # fit is captured in the prepare key but ignored for the circle clip

    spindle_r = max(1.0, disc_diameter_px * 0.0075)
    spindle_paint = skia.Paint(AntiAlias=True)
    spindle_paint.setColor4f(skia.Color4f(0.0, 0.0, 0.0, 1.0))
    canvas.drawCircle(cx, cy, spindle_r, spindle_paint)

    return surface.makeImageSnapshot(), float(side)


def _bake_circle_shadow(
    radius: float,
    dx: float,
    dy: float,
    sigma: float,
    alpha: int,
) -> tuple[skia.Image, float]:
    """Bake a circular drop shadow into a square skia.Image.
    Returns (image, half_side) so the caller can stamp it centered."""
    spread = sigma * 3.0 + max(abs(dx), abs(dy))
    half = math.ceil(radius + spread) + 2
    side = int(half * 2)
    surface = skia.Surface(side, side)
    canvas = surface.getCanvas()
    canvas.clear(skia.ColorTRANSPARENT)
    canvas.translate(half, half)
    paint = skia.Paint(AntiAlias=True)
    paint.setColor4f(skia.Color4f(0.0, 0.0, 0.0, 1.0))
    paint.setImageFilter(
        skia.ImageFilters.DropShadowOnly(dx, dy, sigma, sigma, skia.ColorSetARGB(alpha, 0, 0, 0))
    )
    canvas.drawCircle(0.0, 0.0, radius, paint)
    return surface.makeImageSnapshot(), float(half)


def _bake_square_shadow(
    side_len: float,
    dx: float,
    dy: float,
    sigma: float,
    alpha: int,
) -> tuple[skia.Image, float]:
    """Bake a square drop shadow into a square skia.Image.
    Returns (image, half_side) so the caller can stamp it centered."""
    spread = sigma * 3.0 + max(abs(dx), abs(dy))
    half = math.ceil(side_len / 2.0 + spread) + 2
    side = int(half * 2)
    surface = skia.Surface(side, side)
    canvas = surface.getCanvas()
    canvas.clear(skia.ColorTRANSPARENT)
    canvas.translate(half, half)
    paint = skia.Paint(AntiAlias=True)
    paint.setColor4f(skia.Color4f(0.0, 0.0, 0.0, 1.0))
    paint.setImageFilter(
        skia.ImageFilters.DropShadowOnly(dx, dy, sigma, sigma, skia.ColorSetARGB(alpha, 0, 0, 0))
    )
    canvas.drawRect(skia.Rect.MakeXYWH(-side_len / 2.0, -side_len / 2.0, side_len, side_len), paint)
    return surface.makeImageSnapshot(), float(half)


def _draw_fitted(
    canvas: skia.Canvas,
    bounds: Rect,
    image: skia.Image,
    fit: FitMode,
    paint: skia.Paint,
) -> None:
    src_w, src_h = float(image.width()), float(image.height())
    dst_w, dst_h = float(bounds.width), float(bounds.height)

    if src_w == 0 or src_h == 0:
        return

    src_aspect = src_w / src_h
    dst_aspect = dst_w / dst_h

    match fit:
        case FitMode.CONTAIN:
            s = dst_w / src_w if src_aspect > dst_aspect else dst_h / src_h
            draw_w, draw_h = src_w * s, src_h * s
            dx = bounds.x + (dst_w - draw_w) / 2
            dy = bounds.y + (dst_h - draw_h) / 2
        case FitMode.COVER:
            s = dst_h / src_h if src_aspect > dst_aspect else dst_w / src_w
            draw_w, draw_h = src_w * s, src_h * s
            dx = bounds.x + (dst_w - draw_w) / 2
            dy = bounds.y + (dst_h - draw_h) / 2
        case FitMode.FIT_WIDTH:
            s = dst_w / src_w
            draw_w, draw_h = dst_w, src_h * s
            dx, dy = float(bounds.x), bounds.y + (dst_h - draw_h) / 2
        case FitMode.FIT_HEIGHT:
            s = dst_h / src_h
            draw_w, draw_h = src_w * s, dst_h
            dx, dy = bounds.x + (dst_w - draw_w) / 2, float(bounds.y)
        case _:  # STRETCH
            draw_w, draw_h = dst_w, dst_h
            dx, dy = float(bounds.x), float(bounds.y)

    canvas.drawImageRect(
        image,
        skia.Rect.MakeWH(src_w, src_h),
        skia.Rect.MakeXYWH(dx, dy, draw_w, draw_h),
        skia.SamplingOptions(skia.FilterMode.kLinear),
        paint,
    )
