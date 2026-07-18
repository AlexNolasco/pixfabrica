from pixfabrica_core.plugins import PluginManifest

# audio
from pixfabrica_std.audio.audio_debug import AudioDebug
from pixfabrica_std.audio.capsule_bars_gl import CapsuleBarsGL
from pixfabrica_std.audio.eq_bars_gl import EqBarsGL
from pixfabrica_std.audio.eq_led_gl import EqLedGL
from pixfabrica_std.audio.eq_wave_gl import EqWaveGL
from pixfabrica_std.audio.neon_ring_gl import NeonRingGL
from pixfabrica_std.audio.plasma_ring_gl import PlasmaRingGL
from pixfabrica_std.audio.radial_bars_gl import RadialBarsGL
from pixfabrica_std.audio.radial_rays_gl import RadialRaysGL
from pixfabrica_std.audio.spectrum_bars import SpectrumBars
from pixfabrica_std.audio.star_pulse_gl import StarPulseGL
from pixfabrica_std.audio.vu_meter import VuMeter
from pixfabrica_std.audio.waveform_band import WaveformBand
from pixfabrica_std.audio.waveform_bars import WaveformBars
from pixfabrica_std.audio.waveform_raymarch_gl import WaveformRaymarchGL
from pixfabrica_std.audio.wavy_lines_gl import WavyLinesGL
from pixfabrica_std.background.animated_gradient_gl import AnimatedGradientGL

# background
from pixfabrica_std.background.ascend_gl import AscendGL
from pixfabrica_std.background.campfire_gl import CampfireGL
from pixfabrica_std.background.cosmic_network_gl import CosmicNetworkGL
from pixfabrica_std.background.fade_gradient_gl import FadeGradientGL
from pixfabrica_std.background.fire_base_gl import FireBaseGL
from pixfabrica_std.background.fractal_plasma_gl import FractalPlasmaGL
from pixfabrica_std.background.fuzzy_clouds_gl import FuzzyCloudsGL
from pixfabrica_std.background.gradient import Gradient
from pixfabrica_std.background.heart_dance_gl import HeartDanceGL
from pixfabrica_std.background.heart_fireworks_gl import HeartFireworksGL
from pixfabrica_std.background.hex_background_gl import HexBackgroundGL
from pixfabrica_std.background.hyperspace_gl import HyperspaceGL
from pixfabrica_std.background.inferno_tunnel_gl import InfernoTunnelGL
from pixfabrica_std.background.led_eq_gl import LedEqGL
from pixfabrica_std.background.liquid_metal_gl import LiquidMetalGL
from pixfabrica_std.background.music_room_gl import MusicRoomGL
from pixfabrica_std.background.neon_sunset_gl import NeonSunsetGL
from pixfabrica_std.background.neon_tunnel_gl import NeonTunnelGL
from pixfabrica_std.background.orbit_trail_gl import OrbitTrailGL
from pixfabrica_std.background.scifi_widget_gl import SciFiWidgetGL
from pixfabrica_std.background.sepia_nebula_gl import SepiaNebulaGL
from pixfabrica_std.background.singularity_gl import SingularityGL
from pixfabrica_std.background.solid_background import SolidBackground
from pixfabrica_std.background.star_dust_gl import StarDustGL
from pixfabrica_std.background.star_nest_gl import StarNestGL
from pixfabrica_std.background.sun_gl import SunGL
from pixfabrica_std.background.warped_grid_gl import WarpedGridGL

# config
from pixfabrica_std.config.basic_themes import BasicThemes
from pixfabrica_std.config.default_typography import DefaultTypography

# effects
from pixfabrica_std.effects.border_plasma import BorderPlasmaGL
from pixfabrica_std.effects.digital_glitch import DigitalGlitch
from pixfabrica_std.effects.duotone import Duotone
from pixfabrica_std.effects.glitch import Glitch
from pixfabrica_std.effects.interlaced_glitch import InterlacedGlitch
from pixfabrica_std.effects.palette_cycle_gl import PaletteCycle
from pixfabrica_std.effects.pixelate import Pixelate
from pixfabrica_std.effects.scanlines import Scanlines
from pixfabrica_std.effects.shockwave import Shockwave
from pixfabrica_std.effects.spectrum_glitch import SpectrumGlitch
from pixfabrica_std.effects.speed_lines import SpeedLines
from pixfabrica_std.effects.sweep_lines import SweepLines
from pixfabrica_std.effects.sweep_lines_gl import SweepLinesGL
from pixfabrica_std.effects.vhs_grain import VHSGrain
from pixfabrica_std.effects.vignette import Vignette
from pixfabrica_std.effects.water_drops_gl import WaterDropsGL

# image
from pixfabrica_std.image.background_image import BackgroundImage
from pixfabrica_std.image.image import Image
from pixfabrica_std.image.mockup_eq import MockupEq
from pixfabrica_std.image.svg_icon import SvgIcon
from pixfabrica_std.image.vinyl_record import VinylRecord

# mesh
from pixfabrica_std.mesh.gltf_mesh_gl import GltfMeshGL
from pixfabrica_std.mesh.pixpal_mesh_gl import PixPalMeshGL
from pixfabrica_std.mesh.pixpal_shapekey_mesh_gl import PixPalShapeKeyMeshGL

# particles
from pixfabrica_std.particles.cloud import Cloud
from pixfabrica_std.particles.drifting_dust_gl import DriftingDustGL
from pixfabrica_std.particles.drifting_embers_gl import DriftingEmbersGL
from pixfabrica_std.particles.dying_universe_gl import DyingUniverseGL
from pixfabrica_std.particles.edge_smoke_gl import EdgeSmokeGL
from pixfabrica_std.particles.snow_gl import SnowGL

# player
from pixfabrica_std.player.info_track_card import InfoTrackCard
from pixfabrica_std.player.mini_track_card import MiniTrackCard
from pixfabrica_std.player.track_card import TrackCard

# progress
from pixfabrica_std.progress.circular_progress import CircularProgress
from pixfabrica_std.progress.progress_bar import ProgressBar
from pixfabrica_std.progress.progress_bar_gl import ProgressBarGL
from pixfabrica_std.progress.time_counter import TimeCounter

# text
from pixfabrica_std.text.dynamic_text import DynamicText
from pixfabrica_std.text.glow_text import GlowText
from pixfabrica_std.text.lyrics_camera import LyricsCamera
from pixfabrica_std.text.lyrics_caption import LyricsCaption
from pixfabrica_std.text.lyrics_pop import LyricsPop
from pixfabrica_std.text.marquee import Marquee
from pixfabrica_std.text.path_marquee import PathMarquee
from pixfabrica_std.text.static_text import StaticText
from pixfabrica_std.text.teleprompter_caption import TeleprompterCaption
from pixfabrica_std.text.word_cloud import WordCloud

# utility
from pixfabrica_std.utility.spacer import SpacerGL, SpacerSkia

# video
from pixfabrica_std.video.video import Video

from . import icons as _icons  # noqa: F401 — register_icon side effects


class Plugin:
    manifest = PluginManifest(
        name="pixfabrica-std",
        display_name="Pixfabrica Standard",
        description="Built-in clip library.",
        requires_core=">=0.1.0,<1.0",
    )
    project_settings = [
        BasicThemes,
        DefaultTypography,
    ]
    clip_types = [
        AscendGL,
        AnimatedGradientGL,
        CampfireGL,
        CosmicNetworkGL,
        FractalPlasmaGL,
        FuzzyCloudsGL,
        FadeGradientGL,
        FireBaseGL,
        HeartDanceGL,
        HeartFireworksGL,
        HexBackgroundGL,
        HyperspaceGL,
        InfernoTunnelGL,
        LedEqGL,
        LiquidMetalGL,
        MusicRoomGL,
        NeonSunsetGL,
        NeonTunnelGL,
        OrbitTrailGL,
        SciFiWidgetGL,
        SepiaNebulaGL,
        SingularityGL,
        AudioDebug,
        CapsuleBarsGL,
        EqBarsGL,
        EqLedGL,
        EqWaveGL,
        NeonRingGL,
        PlasmaRingGL,
        RadialBarsGL,
        RadialRaysGL,
        SpectrumBars,
        StarPulseGL,
        VuMeter,
        WaveformBand,
        WaveformBars,
        WaveformRaymarchGL,
        WavyLinesGL,
        BackgroundImage,
        Image,
        MockupEq,
        BorderPlasmaGL,
        Cloud,
        DyingUniverseGL,
        DriftingDustGL,
        DriftingEmbersGL,
        EdgeSmokeGL,
        DynamicText,
        GltfMeshGL,
        PixPalMeshGL,
        PixPalShapeKeyMeshGL,
        GlowText,
        LyricsCaption,
        LyricsCamera,
        LyricsPop,
        Duotone,
        Glitch,
        DigitalGlitch,
        InterlacedGlitch,
        SpectrumGlitch,
        PaletteCycle,
        Gradient,
        Marquee,
        PathMarquee,
        Pixelate,
        Scanlines,
        Shockwave,
        SpeedLines,
        CircularProgress,
        ProgressBar,
        ProgressBarGL,
        TimeCounter,
        InfoTrackCard,
        TrackCard,
        MiniTrackCard,
        SnowGL,
        SolidBackground,
        SpacerGL,
        SpacerSkia,
        StarDustGL,
        StarNestGL,
        SunGL,
        WarpedGridGL,
        StaticText,
        TeleprompterCaption,
        WordCloud,
        SvgIcon,
        SweepLines,
        SweepLinesGL,
        VHSGrain,
        Vignette,
        WaterDropsGL,
        Video,
        VinylRecord,
    ]


__all__ = ["Plugin"]
