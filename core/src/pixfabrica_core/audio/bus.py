from __future__ import annotations

from pydantic import BaseModel

# Log-spaced spectrum bands per frame — HTML5 / p5.FFT logAverages-style contract.
N_SPECTRUM: int = 64

# Legacy mel resolution — removed from bus contract; kept for NPZ migration only.
N_MELS: int = 128


class AudioBusFrame(BaseModel):
    """Per-frame payload published by a sound clip onto a named audio bus.

    ``spectrum`` holds ``N_SPECTRUM`` log-spaced magnitude bands normalised 0..1
    (job-wide). Same mental model as grouping ``AnalyserNode`` linear bins for display.
    """

    spectrum: list[float]
    bass: float
    mid: float
    high: float
    beat: bool
    onset: bool = False
    percussion: bool = False
    amplitude: float

    @classmethod
    def zero(cls) -> AudioBusFrame:
        return cls(
            spectrum=[0.0] * N_SPECTRUM,
            bass=0.0,
            mid=0.0,
            high=0.0,
            beat=False,
            onset=False,
            percussion=False,
            amplitude=0.0,
        )


# bus_name -> list of AudioBusFrame indexed by compositor/video frame (0 … job.total_frames - 1)
AudioTimeline = dict[str, list[AudioBusFrame]]


def effective_bus_name(bus_select: str | None) -> str:
    """Bus key for timeline lookup — unset/blank defaults to ``main`` (clip preview samples)."""
    return (bus_select or "main").strip() or "main"


def bus_timeline_for_select(
    timeline: AudioTimeline,
    bus_select: str | None,
) -> list[AudioBusFrame] | None:
    """Return per-frame bus data for ``bus_select``, or ``None`` when the bus is absent."""
    frames = timeline.get(effective_bus_name(bus_select))
    return frames if frames else None


def resolve_bus_frame(timeline: AudioTimeline, bus: str, frame: int) -> AudioBusFrame:
    """Return the AudioBusFrame for a given bus and frame, or a zero frame if out of range."""
    frames = timeline.get(bus)
    if frames and 0 <= frame < len(frames):
        return frames[frame]
    return AudioBusFrame.zero()


def resolve_bus_frame_for_select(
    timeline: AudioTimeline,
    bus_select: str | None,
    frame: int,
) -> AudioBusFrame:
    """Like ``resolve_bus_frame`` but applies ``effective_bus_name`` for ``bus_select``."""
    return resolve_bus_frame(timeline, effective_bus_name(bus_select), frame)


def resolve_audio_bus_frame_for_clip(
    *,
    audio: AudioTimeline,
    bus_select: str | None,
    frame: int,
) -> AudioBusFrame:
    return resolve_bus_frame_for_select(audio, bus_select, frame)


def align_bus_timeline_to_job(
    timeline: list[AudioBusFrame],
    *,
    sound_start_seconds: float,
    job_total_frames: int,
    fps: float,
) -> list[AudioBusFrame]:
    """Map analyzer output to job timeline frames."""
    if job_total_frames <= 0:
        return []
    pad_raw = max(0, int(round(float(sound_start_seconds) * fps)))
    pad = min(pad_raw, job_total_frames)
    tail_slots = job_total_frames - pad
    body = timeline[:tail_slots]
    zeros_needed = tail_slots - len(body)
    return (
        [AudioBusFrame.zero() for _ in range(pad)]
        + list(body)
        + [AudioBusFrame.zero() for _ in range(zeros_needed)]
    )
