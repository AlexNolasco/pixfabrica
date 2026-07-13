"""Pixfabrica core — shared graph models and types."""

from pixfabrica_core.audio import (
    N_SPECTRUM,
    AudioBusFrame,
    AudioTimeline,
    AudioVisualMixin,
    SoundClip,
    resolve_bus_frame,
)
from pixfabrica_core.clips import Clip, ClipTypeProtocol, DrawableProtocol, VisualClip
from pixfabrica_core.clips.base import ClipCategory, ClipTag
from pixfabrica_core.composition.graph import (
    Graph,
    GraphNode,
    PortConnection,
    PortType,
    Transition,
    topological_sort,
)
from pixfabrica_core.composition.track import TrackTransition, TransitionType
from pixfabrica_core.easing import EasingType, apply_easing
from pixfabrica_core.errors import RenderError, RenderErrorCode
from pixfabrica_core.load_render_job import load_render_job
from pixfabrica_core.plugins import PluginManifest, PluginProtocol
from pixfabrica_core.progress import RenderProgress
from pixfabrica_core.theme.color import ColorPalette

__all__ = [
    "RenderError",
    "RenderErrorCode",
    "RenderProgress",
    "load_render_job",
    "AudioBusFrame",
    "AudioTimeline",
    "AudioVisualMixin",
    "N_SPECTRUM",
    "resolve_bus_frame",
    "SoundClip",
    "EasingType",
    "Graph",
    "GraphNode",
    "ClipCategory",
    "ClipTag",
    "PortConnection",
    "PortType",
    "Transition",
    "TrackTransition",
    "TransitionType",
    "topological_sort",
    "apply_easing",
    "PluginManifest",
    "PluginProtocol",
    "DrawableProtocol",
    "ClipTypeProtocol",
    "Clip",
    "ColorPalette",
    "VisualClip",
]
