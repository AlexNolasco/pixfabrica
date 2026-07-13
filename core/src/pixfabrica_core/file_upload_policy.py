"""File upload policies — declared on clip classes, indexed at catalog build."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pixfabrica_core.upload_manifest import read_upload_manifest

DEFAULT_TARGET_WIDTH = 1920
DEFAULT_TARGET_HEIGHT = 1080


@dataclass(frozen=True, slots=True)
class UploadPolicyContext:
    clip_type: str
    plugin_id: str
    field: str
    kind: str
    target_width: int | None = None
    target_height: int | None = None
    target_fps: float | None = None
    clip_params: dict[str, Any] | None = None


@runtime_checkable
class FileUploadPolicy(Protocol):
    """Clip-declared upload/prepare sizing policy for a file field."""

    def max_px(self, ctx: UploadPolicyContext) -> int: ...

    def max_px_from_bounds(self, width: float, height: float) -> int: ...


@dataclass(frozen=True, slots=True)
class JobBoundsFactorPolicy:
    """Cap long edge at ``factor`` × max(job width, job height)."""

    factor: float = 2.0

    def max_px(self, ctx: UploadPolicyContext) -> int:
        w = ctx.target_width if ctx.target_width is not None else DEFAULT_TARGET_WIDTH
        h = ctx.target_height if ctx.target_height is not None else DEFAULT_TARGET_HEIGHT
        return self.max_px_from_bounds(float(w), float(h))

    def max_px_from_bounds(self, width: float, height: float) -> int:
        return max(1, int(self.factor * max(width, height)))


def _content_long_edge(width: float, height: float, *, padding_x: float, padding_y: float) -> float:
    px = max(0.0, min(0.9, float(padding_x)))
    py = max(0.0, min(0.9, float(padding_y)))
    inner_w = width * (1.0 - px)
    inner_h = height * (1.0 - py)
    return min(inner_w, inner_h)


@dataclass(frozen=True, slots=True)
class ContentThumbFactorPolicy:
    """Cap thumb long edge at ``factor`` × square cover side derived from job bounds.

    Reads optional layout params from ``UploadPolicyContext.clip_params`` when
    present (``padding_x``, ``padding_y``, ``cover_scale``, ``progress_height``,
    ``band_height``).
    """

    factor: float = 2.0
    thumb_max_px: float = 512.0
    cover_scale_param: str = "cover_scale"
    progress_height_param: str = "progress_height"
    band_height_param: str = "band_height"
    padding_x_param: str = "padding_x"
    padding_y_param: str = "padding_y"
    default_cover_scale: float = 0.85
    default_progress_height: float = 0.03
    default_band_height: float = 0.10
    default_padding_x: float = 0.05
    default_padding_y: float = 0.05

    def _params(self, ctx: UploadPolicyContext | None) -> dict[str, Any]:
        if ctx is None or ctx.clip_params is None:
            return {}
        return ctx.clip_params

    def thumb_side_px(
        self,
        width: float,
        height: float,
        *,
        padding_x: float,
        padding_y: float,
        cover_scale: float,
        progress_height: float,
        band_height: float,
    ) -> float:
        py = max(0.0, min(0.9, float(padding_y)))
        card_h = height * max(0.01, min(1.0, float(band_height)))
        progress_px = card_h * max(0.0, min(0.5, float(progress_height)))
        row_h = max(1.0, card_h - progress_px)
        inner_h = row_h * (1.0 - py)
        side = inner_h * max(0.01, min(1.0, float(cover_scale)))
        return min(side, self.thumb_max_px)

    def max_px(self, ctx: UploadPolicyContext) -> int:
        w = float(ctx.target_width if ctx.target_width is not None else DEFAULT_TARGET_WIDTH)
        h = float(ctx.target_height if ctx.target_height is not None else DEFAULT_TARGET_HEIGHT)
        params = self._params(ctx)
        padding_x = float(params.get(self.padding_x_param, self.default_padding_x))
        padding_y = float(params.get(self.padding_y_param, self.default_padding_y))
        cover_scale = float(params.get(self.cover_scale_param, self.default_cover_scale))
        progress_height = float(
            params.get(self.progress_height_param, self.default_progress_height)
        )
        band_height = float(params.get(self.band_height_param, self.default_band_height))
        return self.max_px_from_bounds(
            w,
            h,
            padding_x=padding_x,
            padding_y=padding_y,
            cover_scale=cover_scale,
            progress_height=progress_height,
            band_height=band_height,
        )

    def max_px_from_bounds(
        self,
        width: float,
        height: float,
        *,
        padding_x: float | None = None,
        padding_y: float | None = None,
        cover_scale: float | None = None,
        progress_height: float | None = None,
        band_height: float | None = None,
    ) -> int:
        side = self.thumb_side_px(
            width,
            height,
            padding_x=self.default_padding_x if padding_x is None else padding_x,
            padding_y=self.default_padding_y if padding_y is None else padding_y,
            cover_scale=self.default_cover_scale if cover_scale is None else cover_scale,
            progress_height=self.default_progress_height
            if progress_height is None
            else progress_height,
            band_height=self.default_band_height if band_height is None else band_height,
        )
        return max(1, int(self.factor * side))


def _vinyl_layout_long_edge(width: float, height: float, *, width_frac: float) -> float:
    wf = max(0.0, min(1.0, float(width_frac)))
    return min(width * wf, height)


@dataclass(frozen=True, slots=True)
class DisplayWidthFactorPolicy:
    """Cap long edge at ``factor`` × displayed width (``width_frac`` × job width).

    Reads ``width_param`` from ``UploadPolicyContext.clip_params`` when present.
    """

    factor: float = 2.0
    min_px: int = 64
    width_param: str = "width"
    default_width: float = 0.5

    def _width_frac(self, ctx: UploadPolicyContext | None) -> float:
        params = {} if ctx is None or ctx.clip_params is None else ctx.clip_params
        try:
            width_frac = float(params.get(self.width_param, self.default_width))
        except (TypeError, ValueError):
            width_frac = self.default_width
        return max(0.01, min(1.0, width_frac))

    def max_px(self, ctx: UploadPolicyContext) -> int:
        w = float(ctx.target_width if ctx.target_width is not None else DEFAULT_TARGET_WIDTH)
        return self.max_px_from_bounds(w, 0.0, width_frac=self._width_frac(ctx))

    def max_px_from_bounds(
        self,
        width: float,
        height: float,
        *,
        width_frac: float | None = None,
    ) -> int:
        del height  # displayed width depends only on job width for this policy
        frac = self.default_width if width_frac is None else max(0.01, min(1.0, float(width_frac)))
        display_w = frac * width
        return max(self.min_px, int(self.factor * display_w))


@dataclass(frozen=True, slots=True)
class VinylCoverFactorPolicy:
    """Cap cover long edge at ``factor`` × disc diameter (bounded by ``disc_bake_max_px``)."""

    factor: float = 2.0
    disc_bake_max_px: float = 768.0

    def cover_max_px(
        self,
        width: float,
        height: float,
        *,
        width_frac: float = 1.0,
    ) -> int:
        disc = min(
            _vinyl_layout_long_edge(width, height, width_frac=width_frac),
            self.disc_bake_max_px,
        )
        return max(1, int(self.factor * disc))

    def max_px(self, ctx: UploadPolicyContext) -> int:
        w = float(ctx.target_width if ctx.target_width is not None else DEFAULT_TARGET_WIDTH)
        h = float(ctx.target_height if ctx.target_height is not None else DEFAULT_TARGET_HEIGHT)
        params = ctx.clip_params or {}
        width_frac = float(params.get("width", 1.0))
        return self.cover_max_px(w, h, width_frac=width_frac)

    def max_px_from_bounds(self, width: float, height: float) -> int:
        return self.cover_max_px(width, height)


@dataclass(frozen=True, slots=True)
class ImageOptimizedFor:
    width: int
    height: int


def collect_file_upload_policies(type_cls: type) -> dict[str, FileUploadPolicy]:
    """Read policy hooks from a clip class (``file_upload_policies`` or ``source_upload_policy``)."""
    policies: dict[str, FileUploadPolicy] = {}

    batch = getattr(type_cls, "file_upload_policies", None)
    if callable(batch):
        raw = batch()
        if isinstance(raw, dict):
            for field, policy in raw.items():
                if isinstance(field, str) and isinstance(policy, FileUploadPolicy):
                    policies[field] = policy

    single = getattr(type_cls, "source_upload_policy", None)
    if callable(single) and "source" not in policies:
        policy = single()
        if isinstance(policy, FileUploadPolicy):
            policies["source"] = policy

    return policies


def lookup_file_upload_policy(
    policies: dict[tuple[str, str], FileUploadPolicy],
    *,
    clip_type: str,
    field: str,
) -> FileUploadPolicy | None:
    return policies.get((clip_type, field))


def manifest_covers_max_px(media_path: Path, max_px: int) -> bool:
    """True when an upload manifest records dimensions already within ``max_px``."""
    manifest = read_upload_manifest(media_path)
    if manifest is None:
        return False
    raw = manifest.get("optimized_for")
    if not isinstance(raw, dict):
        return False
    try:
        width = int(raw["width"])
        height = int(raw["height"])
    except (KeyError, TypeError, ValueError):
        return False
    return max(width, height) <= max_px


def optimized_for_payload(image: ImageOptimizedFor, *, fps: float = 0.0) -> dict[str, int | float]:
    return {"width": image.width, "height": image.height, "fps": fps}


def build_file_upload_policy_index(
    plugins: list[Any],
) -> dict[tuple[str, str], FileUploadPolicy]:
    """Build ``(clip_type, field)`` → policy from discovered plugin clip classes."""
    index: dict[tuple[str, str], FileUploadPolicy] = {}
    for plugin in plugins:
        for clip_cls in plugin.clip_types:
            clip_type = getattr(clip_cls, "clip_type", None)
            if not clip_type:
                continue
            for field, policy in collect_file_upload_policies(clip_cls).items():
                index[(clip_type, field)] = policy
    return index
