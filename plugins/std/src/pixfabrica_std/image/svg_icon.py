from __future__ import annotations

import asyncio
import hashlib
import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import ClassVar

import numpy as np
import skia
from pydantic import Field, PrivateAttr

from pixfabrica_core.audio.mixin import AudioVisualMixin
from pixfabrica_core.clips import ClipCategory, ClipSkia, ClipTag, PrepareContext, RenderContext
from pixfabrica_core.graphics import Rect
from pixfabrica_core.prepare_diagnostics import record_prepare_asset_failure
from pixfabrica_core.theme.color import Color, ColorToken, color_field, resolve_color
from pixfabrica_std.mesh.shader_helper import precompute_bass_drive
from pixfabrica_std.tilt import ANGLE_FULL_DESC, ANGLE_FULL_MAX, ANGLE_FULL_MIN

log = logging.getLogger("pixfabrica.std.svg_icon")

# Register namespaces once so ET serialises without ns0: mangling.
ET.register_namespace("", "http://www.w3.org/2000/svg")
ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")


class SvgIcon(AudioVisualMixin, ClipSkia):
    """Vector SVG icon or logo with optional audio-reactive scale pulse.

    Accepts a local file path, http(s) URL, or an inline SVG string.
    Works without a bus_select — displays at base size when no audio is wired.
    """

    clip_type: ClassVar[str] = "std-svg-icon"
    clip_category: ClassVar[ClipCategory] = ClipCategory.IMAGE
    clip_tags: ClassVar[list[str]] = [ClipTag.AUDIO_REACTIVE]

    source: str = Field(default="", description="Local file path, http(s) URL")
    color: ColorToken | Color = color_field(ColorToken.PRIMARY)
    offset_x: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Horizontal center as fraction of bounds width (0=left, 1=right)",
    )
    offset_y: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        multiple_of=0.01,
        description="Vertical center as fraction of bounds height (0=top, 1=bottom)",
    )
    size: float = Field(
        default=0.25,
        ge=0.01,
        le=2.0,
        multiple_of=0.01,
        description="Icon diameter as fraction of min(bounds.width, bounds.height)",
    )
    angle: float = Field(
        default=0.0,
        ge=ANGLE_FULL_MIN,
        le=ANGLE_FULL_MAX,
        multiple_of=1.0,
        description=ANGLE_FULL_DESC,
    )
    opacity: float = Field(default=1.0, ge=0.0, le=1.0, description="Overall layer opacity")
    sensitivity: float = Field(
        default=0.15,
        ge=0.0,
        le=1.0,
        description="Max additive scale at full bass (0 = no reactivity)",
    )

    _dom: skia.SVGDOM | None = PrivateAttr(default=None)
    _prepare_key: tuple | None = PrivateAttr(default=None)
    _bass_history: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype=np.float32))

    async def prepare(self, ctx: PrepareContext, bounds: Rect | None = None) -> None:
        total = max(ctx.job.total_frames, 0)
        self._bass_history = precompute_bass_drive(self.bus_timeline(ctx), total)
        if not self.source:
            return
        await asyncio.to_thread(self._prepare_sync, ctx)

    def _prepare_sync(self, ctx: PrepareContext) -> None:
        resolved_color = resolve_color(self.color, ctx.job.colors)
        key = (self.source, resolved_color.rgba)
        if key == self._prepare_key:
            return

        try:
            path = _resolve_source_sync(self.source, ctx)
            svg_bytes = path.read_bytes()

            svg_bytes = _normalize_svg(svg_bytes)

            if True:
                r, g, b, _ = resolved_color.rgba
                hex_color = f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"
                svg_bytes = (
                    svg_bytes.decode("utf-8", errors="replace")
                    .replace("currentColor", hex_color)
                    .encode()
                )

            self._dom = skia.SVGDOM.MakeFromStream(skia.MemoryStream(svg_bytes))
            if self._dom is None:
                log.warning("SvgIcon %s: Skia could not parse SVG from %r", self.id, self.source)
                record_prepare_asset_failure(
                    ctx,
                    kind="clip",
                    ref_id=self.id,
                    clip_type=self.clip_type,
                    field="source",
                    source=self.source,
                    exc=RuntimeError("could not parse SVG"),
                    code="load_failed",
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
            log.warning("SvgIcon %s: failed to load SVG — %s", self.id, exc)
            self._dom = None

        self._prepare_key = key

    def _bass_drive_for_frame(self, ctx: RenderContext) -> float:
        if not self.bus_active_for_draw(ctx):
            return 0.0
        if self._bass_history.shape[0] > 0:
            f = max(0, min(ctx.time.frame, self._bass_history.shape[0] - 1))
            return min(1.0, float(self._bass_history[f]))
        return min(1.0, max(0.0, float(ctx.audio_bus_frame.bass)))

    def draw(self, ctx: RenderContext) -> None:
        if self._dom is None:
            return

        canvas: skia.Canvas = ctx.canvas
        b = ctx.bounds

        bass = self._bass_drive_for_frame(ctx)
        eff_size = self.size * min(b.width, b.height) * (1.0 + self.sensitivity * bass)
        if eff_size <= 0:
            return

        self._dom.setContainerSize(skia.Size(eff_size, eff_size))

        cx = b.x + self.offset_x * b.width
        cy = b.y + self.offset_y * b.height

        canvas.save()
        canvas.clipRect(skia.Rect.MakeXYWH(b.x, b.y, b.width, b.height))
        canvas.translate(cx, cy)
        if self.angle:
            canvas.rotate(self.angle)
        canvas.translate(-eff_size / 2.0, -eff_size / 2.0)

        if self.opacity < 1.0:
            paint = skia.Paint()
            paint.setAlphaf(self.opacity)
            canvas.saveLayer(skia.Rect.MakeWH(eff_size, eff_size), paint)
            self._dom.render(canvas)
            canvas.restore()
        else:
            self._dom.render(canvas)

        canvas.restore()


_FIXED_UNITS = ("px", "pt", "mm", "cm", "in", "pc")


def _normalize_svg(svg_bytes: bytes) -> bytes:
    """Prepare SVG bytes for Skia's limited renderer:

    1. Convert inline style= CSS to presentation attributes — Skia ignores style=.
    2. Replace fixed-unit width/height on the root <svg> with "100%" when a viewBox
       is present, so setContainerSize() controls the rendered size.

    Falls back to the original bytes if XML parsing fails.
    """
    try:
        root = ET.fromstring(svg_bytes)

        # --- Pass 1: style= → presentation attributes (all elements) ---
        for elem in root.iter():
            style = elem.get("style")
            if not style:
                continue
            for decl in style.split(";"):
                prop, sep, val = decl.strip().partition(":")
                if sep and (prop := prop.strip()) and (val := val.strip()):
                    elem.set(prop, val)
            del elem.attrib["style"]

        # --- Pass 2: fix root <svg> size so setContainerSize() takes effect ---
        if root.get("viewBox"):
            for attr in ("width", "height"):
                val = root.get(attr, "")
                if any(val.endswith(u) for u in _FIXED_UNITS) or val.replace(".", "", 1).isdigit():
                    root.set(attr, "100%")

        return ET.tostring(root, encoding="unicode", xml_declaration=False).encode("utf-8")
    except ET.ParseError:
        return svg_bytes


def _resolve_source_sync(source: str, ctx: PrepareContext) -> Path:
    import httpx

    if source.startswith(("http://", "https://")):
        cache_dir = ctx.cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)
        url_hash = hashlib.sha256(source.encode()).hexdigest()
        ext = Path(source.split("?")[0]).suffix or ".svg"
        cached = cache_dir / f"{url_hash}{ext}"
        if not cached.exists():
            tmp = cache_dir / f"{url_hash}.tmp"
            with httpx.Client() as client:
                response = client.get(source)
                response.raise_for_status()
                tmp.write_bytes(response.content)
            tmp.replace(cached)
        return cached

    return Path(source)
