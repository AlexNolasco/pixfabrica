from pixfabrica_core.plugins import PluginManifest
from pixfabrica_std_effects.effects.blur_skia import BlurSkia
from pixfabrica_std_effects.effects.colorize_gl import ColorizeGL
from pixfabrica_std_effects.effects.float_gl import FloatGL
from pixfabrica_std_effects.effects.invert_gl import InvertGL
from pixfabrica_std_effects.effects.saturation_gl import SaturationGL
from pixfabrica_std_effects.effects.shake_skia import ShakeSkia
from pixfabrica_std_effects.effects.signal_skia import SignalSkia
from pixfabrica_std_effects.effects.sway_gl import SwayGL
from pixfabrica_std_effects.effects.tvbug_gl import TvbugGL

__all__ = ["Plugin"]


class Plugin:
    manifest = PluginManifest(
        name="pixfabrica-std-effects",
        display_name="Pixfabrica Standard Effects",
        description="Per-clip GL and Skia effects (lightweight; always-on in dev).",
        requires_core=">=0.1.0,<1.0",
    )
    clip_types: list[type] = []
    effects = [
        BlurSkia,
        ColorizeGL,
        FloatGL,
        InvertGL,
        SaturationGL,
        ShakeSkia,
        SignalSkia,
        SwayGL,
        TvbugGL,
    ]
