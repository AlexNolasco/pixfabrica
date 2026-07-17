"""Lyrics camera — bake a full lyric sheet, then ease a tilted camera over it."""

from __future__ import annotations

import logging
import math
from typing import ClassVar, Literal

import numpy as np
import skia
from pydantic import Field, PrivateAttr

from pixfabrica_core.clips import ClipCategory, ClipSkia, ClipTag, PrepareContext, RenderContext
from pixfabrica_core.graphics import Rect
from pixfabrica_core.lyrics import CaptionSegment
from pixfabrica_core.prepare_diagnostics import record_prepare_asset_failure
from pixfabrica_core.theme.color import Color, ColorToken, color_field, resolve_color
from pixfabrica_core.theme.typography import FontRole, FontSpec
from pixfabrica_std.text.lyrics_caption import (
    _parse,
    _resolve_source_sync,
    _WordItem,
)
from pixfabrica_std.text.skia_font import make_typography_font
from pixfabrica_std.text.teleprompter_caption import (
    _compute_layout,
    _scroll_target_index,
)
from pixfabrica_std.tilt import ANGLE_FULL_DESC, ANGLE_FULL_MAX, ANGLE_FULL_MIN

log = logging.getLogger("pixfabrica.std.lyrics_camera")

# Extra sheet margin so context framing near the first/last segment has room.
_SHEET_PAD_LINES = 1.5
# Soft cap on baked sheet height (px). Longer lyric sets are scaled to fit.
_MAX_SHEET_HEIGHT = 8192
_MAX_SHEET_WIDTH = 4096


class LyricsCamera(ClipSkia):
    """Dynamic lyrics via a prepared sheet and a smooth, tilted camera follow.

    ``prepare()`` lays out every caption segment into one transparent Skia image
    and precomputes a per-frame camera focus (sheet X/Y + scale). ``draw()``
    looks up that camera, applies Z rotation (``angle``), perspective pitch
    (``pitch``), and optionally a fake DOF pass: blur the viewport crop and keep
    a sharp band around the focus line.
    """

    clip_type: ClassVar[str] = "std-lyrics-camera"
    clip_category: ClassVar[ClipCategory] = ClipCategory.TEXT
    clip_tags: ClassVar[list[str]] = [ClipTag.ANIMATED]

    source: str = Field(
        default="", description="Local path or http(s) URL to LRC, SRT, VTT, or WhisperX JSON"
    )
    typography_role: FontRole = Field(
        default="body_medium", description="Typography role from the job theme"
    )
    color: ColorToken | Color = color_field(ColorToken.NEUTRAL)
    lyrics_offset: float = Field(
        default=0.0,
        description="Shift lyric timings by this many seconds (positive = show later)",
    )
    offset_x: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Horizontal camera anchor in the viewport (0=left, 1=right)",
    )
    offset_y: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Vertical camera anchor in the viewport (0=top, 1=bottom)",
    )
    opacity: float = Field(default=1.0, ge=0.0, le=1.0, multiple_of=0.1)
    align: Literal["left", "center", "right"] = Field(default="center")
    wrap_width: float = Field(
        default=0.85,
        ge=0.1,
        le=1.0,
        multiple_of=0.05,
        description="Max text block width as fraction of bounds width",
    )
    angle: float = Field(
        default=5.0,
        ge=ANGLE_FULL_MIN,
        le=ANGLE_FULL_MAX,
        multiple_of=1.0,
        description=ANGLE_FULL_DESC,
    )
    pitch: float = Field(
        default=12.0,
        ge=-35.0,
        le=35.0,
        multiple_of=1.0,
        description=(
            "Perspective pitch in degrees (positive = look down the sheet, "
            "top edge farther; negative = look up)"
        ),
    )
    context_lines: int = Field(
        default=3,
        ge=1,
        le=12,
        description="Approx. number of typographic lines visible in the viewport",
    )
    follow_speed: float = Field(
        default=8.0,
        ge=0.5,
        le=30.0,
        multiple_of=0.1,
        description="Exponential decay rate for smooth camera follow (higher = snappier)",
    )
    dof_strength: float = Field(
        default=0.55,
        ge=0.0,
        le=1.0,
        multiple_of=0.05,
        description="Fake depth of field: 0 = off, 1 = strong blur away from the focus line",
    )

    _segments: list[CaptionSegment] = PrivateAttr(default_factory=list)
    _prepare_key: tuple | None = PrivateAttr(default=None)
    _layout: list[tuple[list[list[_WordItem]], float]] | None = PrivateAttr(default=None)
    _cumulative_y: list[float] = PrivateAttr(default_factory=list)
    _sheet: skia.Image | None = PrivateAttr(default=None)
    _sheet_scale: float = PrivateAttr(default=1.0)
    _pad_x: float = PrivateAttr(default=0.0)
    _pad_y: float = PrivateAttr(default=0.0)
    # Per-frame camera focus in sheet pixels (x, y) and uniform scale.
    _cam_x: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype="f4"))
    _cam_y: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype="f4"))
    _cam_scale: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype="f4"))
    _line_h: float = PrivateAttr(default=0.0)
    _max_w: float = PrivateAttr(default=0.0)

    async def prepare(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        import asyncio

        if not self.source:
            return
        b = bounds or Rect(0, 0, ctx.job.width, ctx.job.height)
        key = (
            self.source,
            round(b.width, 1),
            round(b.height, 1),
            self.typography_role,
            self.wrap_width,
            self.align,
            self.context_lines,
            self.follow_speed,
            self.lyrics_offset,
            self.start,
            str(self.color),
            ctx.job.fps,
            ctx.job.total_frames,
        )
        if key == self._prepare_key:
            return
        await asyncio.to_thread(self._prepare_sync, ctx, b)
        self._prepare_key = key

    def _prepare_sync(self, ctx: PrepareContext, bounds: Rect) -> None:
        self._sheet = None
        self._layout = None
        self._cam_x = np.zeros(0, dtype="f4")
        self._cam_y = np.zeros(0, dtype="f4")
        self._cam_scale = np.zeros(0, dtype="f4")

        try:
            path = _resolve_source_sync(self.source, ctx)
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
            log.warning("LyricsCamera %s: could not resolve %r — %s", self.id, self.source, exc)
            return
        try:
            self._segments = _parse(path)
            log.debug("LyricsCamera %s: loaded %d segments", self.id, len(self._segments))
        except Exception as exc:
            log.warning("LyricsCamera %s: parse failed — %s", self.id, exc)
            return

        if not self._segments:
            return

        spec: FontSpec = getattr(ctx.job.typography, self.typography_role)
        font = make_typography_font(spec)
        metrics = font.getMetrics()
        line_h = (-metrics.fAscent + metrics.fDescent) * spec.line_height
        space_w = font.measureText(" ")
        max_w = bounds.width * self.wrap_width

        self._line_h = line_h
        self._max_w = max_w
        self._layout, self._cumulative_y = _compute_layout(
            self._segments, font, space_w, max_w, line_h
        )

        total_content_h = self._cumulative_y[-1]
        pad_y = line_h * _SHEET_PAD_LINES
        pad_x = max(8.0, line_h * 0.25)
        sheet_w = max_w + 2.0 * pad_x
        sheet_h = total_content_h + 2.0 * pad_y

        # Fit within soft GPU/surface limits while keeping aspect.
        fit = 1.0
        if sheet_w > _MAX_SHEET_WIDTH:
            fit = min(fit, _MAX_SHEET_WIDTH / sheet_w)
        if sheet_h > _MAX_SHEET_HEIGHT:
            fit = min(fit, _MAX_SHEET_HEIGHT / sheet_h)
        self._sheet_scale = fit
        self._pad_x = pad_x * fit
        self._pad_y = pad_y * fit

        bake_w = max(1, int(math.ceil(sheet_w * fit)))
        bake_h = max(1, int(math.ceil(sheet_h * fit)))
        self._sheet = self._bake_sheet(
            font=font,
            metrics=metrics,
            space_w=space_w,
            line_h=line_h,
            max_w=max_w,
            bake_w=bake_w,
            bake_h=bake_h,
            fit=fit,
            pad_x=pad_x,
            pad_y=pad_y,
            color=resolve_color(self.color, ctx.job.colors),
        )

        target_scale = self._framing_scale(bounds.height, line_h, fit)
        self._cam_x, self._cam_y, self._cam_scale = self._precompute_camera(
            fps=ctx.job.fps,
            total_frames=ctx.job.total_frames,
            target_scale=target_scale,
            fit=fit,
            pad_x=pad_x,
            pad_y=pad_y,
            max_w=max_w,
        )

    def _framing_scale(self, viewport_h: float, line_h: float, fit: float) -> float:
        """Uniform scale so roughly ``context_lines`` of sheet lines fill the viewport."""
        visible = max(1, self.context_lines) * line_h * fit
        if visible <= 1e-6:
            return 1.0
        return float(viewport_h) / visible

    def _segment_focus(
        self,
        idx: int,
        *,
        fit: float,
        pad_x: float,
        pad_y: float,
        max_w: float,
    ) -> tuple[float, float]:
        assert self._layout is not None
        seg_h = self._layout[idx][1]
        focus_y = (pad_y + self._cumulative_y[idx] + seg_h / 2.0) * fit
        # Horizontal focus stays on the text column center (align only affects glyphs).
        focus_x = (pad_x + max_w / 2.0) * fit
        return focus_x, focus_y

    def _precompute_camera(
        self,
        *,
        fps: float,
        total_frames: int,
        target_scale: float,
        fit: float,
        pad_x: float,
        pad_y: float,
        max_w: float,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        n = max(total_frames, 0)
        xs = np.zeros(n, dtype="f4")
        ys = np.zeros(n, dtype="f4")
        scales = np.zeros(n, dtype="f4")
        if n == 0 or not self._segments or self._layout is None:
            return xs, ys, scales

        delta_t = 1.0 / fps
        alpha = 1.0 - math.exp(-self.follow_speed * delta_t)
        cam_x, cam_y = self._segment_focus(0, fit=fit, pad_x=pad_x, pad_y=pad_y, max_w=max_w)
        cam_s = target_scale
        primed = False
        for f in range(n):
            t = f / fps
            lyrics_t = t - self.start + self.lyrics_offset
            target_idx = _scroll_target_index(self._segments, lyrics_t)
            tx, ty = self._segment_focus(target_idx, fit=fit, pad_x=pad_x, pad_y=pad_y, max_w=max_w)
            if not primed:
                cam_x, cam_y, cam_s = tx, ty, target_scale
                primed = True
            else:
                cam_x += (tx - cam_x) * alpha
                cam_y += (ty - cam_y) * alpha
                cam_s += (target_scale - cam_s) * alpha
            xs[f] = cam_x
            ys[f] = cam_y
            scales[f] = cam_s
        return xs, ys, scales

    def _bake_sheet(
        self,
        *,
        font: skia.Font,
        metrics: skia.FontMetrics,
        space_w: float,
        line_h: float,
        max_w: float,
        bake_w: int,
        bake_h: int,
        fit: float,
        pad_x: float,
        pad_y: float,
        color: Color,
    ) -> skia.Image:
        assert self._layout is not None
        surface = skia.Surface(bake_w, bake_h)
        canvas = surface.getCanvas()
        canvas.clear(skia.ColorTRANSPARENT)
        if fit != 1.0:
            canvas.scale(fit, fit)

        r, g, b, a = color.rgba
        paint = skia.Paint(AntiAlias=True)
        paint.setColor4f(skia.Color4f(r, g, b, a))

        for i, (lines, _seg_h) in enumerate(self._layout):
            y = pad_y + self._cumulative_y[i]
            for line in lines:
                line_w = sum(item[2] for item in line) + space_w * max(len(line) - 1, 0)
                match self.align:
                    case "left":
                        x = pad_x
                    case "right":
                        x = pad_x + max_w - line_w
                    case _:
                        x = pad_x + (max_w - line_w) / 2.0
                baseline = y - metrics.fAscent
                for j, (word_text, _, word_w) in enumerate(line):
                    if j > 0:
                        x += space_w
                    canvas.drawString(word_text, x, baseline, font, paint)
                    x += word_w
                y += line_h

        return surface.makeImageSnapshot()

    def _camera_state(self, frame: int) -> tuple[float, float, float] | None:
        if self._sheet is None or self._cam_y.size == 0:
            return None
        f_idx = max(0, min(frame, self._cam_y.shape[0] - 1))
        scale = float(self._cam_scale[f_idx])
        if scale <= 0.0:
            return None
        return float(self._cam_x[f_idx]), float(self._cam_y[f_idx]), scale

    def _pitch_persp_y(self, viewport_h: float) -> float:
        """Skia perspY for ``pitch`` degrees, scaled so preview/export feel similar.

        Positive pitch looks down the sheet (content above the focus shrinks).
        """
        if abs(self.pitch) < 0.05:
            return 0.0
        ref = max(float(viewport_h), 1.0)
        return -math.tan(math.radians(float(self.pitch))) / ref

    def _paint_sheet(
        self,
        canvas: skia.Canvas,
        *,
        anchor_x: float,
        anchor_y: float,
        focus_x: float,
        focus_y: float,
        scale: float,
        persp_y: float = 0.0,
        paint: skia.Paint | None = None,
    ) -> None:
        canvas.translate(anchor_x, anchor_y)
        if abs(persp_y) > 1e-9:
            pitch_m = skia.Matrix()
            pitch_m.setPerspY(persp_y)
            canvas.concat(pitch_m)
        canvas.rotate(self.angle)
        canvas.scale(scale, scale)
        canvas.translate(-focus_x, -focus_y)
        canvas.drawImage(self._sheet, 0.0, 0.0, paint=paint)

    def _dof_sigma(self, viewport_w: float, viewport_h: float) -> float:
        """Blur sigma in px from ``dof_strength`` (scales lightly with viewport size)."""
        if self.dof_strength <= 0.0:
            return 0.0
        base = max(4.0, 0.022 * min(viewport_w, viewport_h))
        return float(self.dof_strength) * base

    def _focus_mask_shader(self, w: float, h: float) -> skia.Shader:
        """Vertical alpha ramp: opaque at the camera anchor, soft toward the edges."""
        cy = self.offset_y * h
        # Keep roughly one typographic line sharp; fall off across neighbor context.
        half_sharp = 0.5 * (h / max(self.context_lines, 1))
        falloff = max(h * 0.42, half_sharp * 2.5)

        def _pos(y: float) -> float:
            return float(max(0.0, min(1.0, y / h))) if h > 1e-6 else 0.0

        return skia.GradientShader.MakeLinear(
            points=[(0.0, 0.0), (0.0, h)],
            colors=[
                skia.Color4f(1.0, 1.0, 1.0, 0.0),
                skia.Color4f(1.0, 1.0, 1.0, 0.0),
                skia.Color4f(1.0, 1.0, 1.0, 1.0),
                skia.Color4f(1.0, 1.0, 1.0, 1.0),
                skia.Color4f(1.0, 1.0, 1.0, 0.0),
                skia.Color4f(1.0, 1.0, 1.0, 0.0),
            ],
            positions=[
                0.0,
                _pos(cy - falloff),
                _pos(cy - half_sharp),
                _pos(cy + half_sharp),
                _pos(cy + falloff),
                1.0,
            ],
        )

    def _render_sharp_viewport(
        self,
        *,
        w: int,
        h: int,
        focus_x: float,
        focus_y: float,
        scale: float,
    ) -> skia.Image:
        surf = skia.Surface(w, h)
        c = surf.getCanvas()
        c.clear(skia.ColorTRANSPARENT)
        self._paint_sheet(
            c,
            anchor_x=self.offset_x * w,
            anchor_y=self.offset_y * h,
            focus_x=focus_x,
            focus_y=focus_y,
            scale=scale,
            persp_y=self._pitch_persp_y(float(h)),
        )
        return surf.makeImageSnapshot()

    def _blur_image(self, image: skia.Image, sigma: float) -> skia.Image:
        w, h = int(image.width()), int(image.height())
        surf = skia.Surface(w, h)
        c = surf.getCanvas()
        c.clear(skia.ColorTRANSPARENT)
        paint = skia.Paint()
        paint.setImageFilter(skia.ImageFilters.Blur(sigma, sigma))
        c.drawImage(image, 0.0, 0.0, paint=paint)
        return surf.makeImageSnapshot()

    def draw(self, ctx: RenderContext) -> None:
        cam = self._camera_state(ctx.time.frame)
        if cam is None:
            return
        focus_x, focus_y, scale = cam

        canvas: skia.Canvas = ctx.canvas
        b = ctx.bounds
        paint = skia.Paint()
        paint.setAlphaf(self.opacity)
        persp_y = self._pitch_persp_y(b.height)

        sigma = self._dof_sigma(b.width, b.height)
        if sigma <= 0.05:
            canvas.save()
            canvas.clipRect(skia.Rect.MakeXYWH(b.x, b.y, b.width, b.height))
            self._paint_sheet(
                canvas,
                anchor_x=b.x + self.offset_x * b.width,
                anchor_y=b.y + self.offset_y * b.height,
                focus_x=focus_x,
                focus_y=focus_y,
                scale=scale,
                persp_y=persp_y,
                paint=paint,
            )
            canvas.restore()
            return

        w = max(1, int(round(b.width)))
        h = max(1, int(round(b.height)))
        sharp = self._render_sharp_viewport(w=w, h=h, focus_x=focus_x, focus_y=focus_y, scale=scale)
        blurred = self._blur_image(sharp, sigma)

        canvas.save()
        canvas.clipRect(skia.Rect.MakeXYWH(b.x, b.y, b.width, b.height))
        canvas.translate(b.x, b.y)

        canvas.drawImage(blurred, 0.0, 0.0, paint=paint)

        # Composite sharp text only inside the focus band (DstIn with a Y gradient).
        canvas.saveLayer(skia.Rect.MakeWH(float(w), float(h)), paint)
        canvas.drawImage(sharp, 0.0, 0.0)
        mask = skia.Paint()
        mask.setShader(self._focus_mask_shader(float(w), float(h)))
        mask.setBlendMode(skia.BlendMode.kDstIn)
        canvas.drawRect(skia.Rect.MakeWH(float(w), float(h)), mask)
        canvas.restore()

        canvas.restore()
