"""Clip-local burst envelopes for Bad Signal (procedural + audio layers)."""

from __future__ import annotations

import math

import numpy as np

from pixfabrica_core.audio.bus import AudioBusFrame
from pixfabrica_core.random import SeededRandom

DECAY_ENVELOPE: tuple[float, ...] = (1.0, 0.6, 0.25, 0.05)
FALLBACK_INTERVAL_MIN_S = 2.0
FALLBACK_INTERVAL_MAX_S = 4.0
AMPLITUDE_GATE = 0.3
AMPLITUDE_SPIKE_DELTA = 0.15
MAX_RGB_OFFSET_UV = 0.035
MAX_SLICE_SHIFT_UV = 0.06
BAND_HEIGHT_FINE_PX = 12.0
BAND_HEIGHT_COARSE_PX = 24.0
BAND_HEIGHT_THRESHOLD_PX = 300.0


def hash1d(x: float) -> float:
    return math.sin(x * 127.1) * 43758.5453 % 1.0


def band_height_px(clip_height: float) -> float:
    base = BAND_HEIGHT_FINE_PX if clip_height <= BAND_HEIGHT_THRESHOLD_PX else BAND_HEIGHT_COARSE_PX
    return max(base, 1.0)


def _passes_sensitivity(amplitude: float, sensitivity: float) -> bool:
    if sensitivity <= 0.0:
        return True
    return amplitude > sensitivity * AMPLITUDE_GATE


def _stamp_burst(
    intensity: np.ndarray,
    burst_seed: np.ndarray,
    rgb_sign: np.ndarray,
    start_frame: int,
    seed: float,
    sign: float,
) -> None:
    for i, decay in enumerate(DECAY_ENVELOPE):
        f = start_frame + i
        if f >= len(intensity):
            break
        if decay >= intensity[f]:
            intensity[f] = decay
            burst_seed[f] = seed
            rgb_sign[f] = sign


def precompute_procedural_bursts(
    *,
    total_frames: int,
    fps: float,
    clip_id: str,
    seed: int | None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Scheduled micro-bursts on an clip-local timeline (0 = clip start)."""
    intensity = np.zeros(total_frames, dtype=np.float32)
    burst_seed = np.zeros(total_frames, dtype=np.float32)
    rgb_sign = np.ones(total_frames, dtype=np.float32)

    if total_frames <= 0:
        return intensity, burst_seed, rgb_sign

    rng = SeededRandom(seed) if seed is not None else SeededRandom.from_string(clip_id)
    frame = int(rng.next() * fps * 0.5)
    while frame < total_frames:
        _stamp_burst(
            intensity,
            burst_seed,
            rgb_sign,
            frame,
            rng.next() * 10000.0,
            1.0 if rng.next() >= 0.5 else -1.0,
        )
        gap_s = FALLBACK_INTERVAL_MIN_S + rng.next() * (
            FALLBACK_INTERVAL_MAX_S - FALLBACK_INTERVAL_MIN_S
        )
        frame += max(1, int(gap_s * fps))

    return intensity, burst_seed, rgb_sign


def precompute_audio_bursts(
    *,
    total_frames: int,
    clip_start_frame: int,
    clip_id: str,
    seed: int | None,
    sensitivity: float,
    bus_frames: list[AudioBusFrame] | None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Onset / amplitude-spike bursts mapped into clip-local frame indices."""
    intensity = np.zeros(total_frames, dtype=np.float32)
    burst_seed = np.zeros(total_frames, dtype=np.float32)
    rgb_sign = np.ones(total_frames, dtype=np.float32)

    if total_frames <= 0 or not bus_frames:
        return intensity, burst_seed, rgb_sign

    rng = SeededRandom(seed) if seed is not None else SeededRandom.from_string(clip_id)
    end_frame = clip_start_frame + total_frames
    n = min(len(bus_frames), end_frame)

    local_has_onsets = any(
        bus_frames[clip_start_frame + lf].onset
        for lf in range(total_frames)
        if clip_start_frame + lf < n
    )

    if local_has_onsets:
        for lf in range(total_frames):
            gf = clip_start_frame + lf
            if gf >= n:
                break
            af = bus_frames[gf]
            if af.onset and _passes_sensitivity(af.amplitude, sensitivity):
                _stamp_burst(
                    intensity,
                    burst_seed,
                    rgb_sign,
                    lf,
                    rng.next() * 10000.0,
                    1.0 if rng.next() >= 0.5 else -1.0,
                )
    else:
        for lf in range(1, total_frames):
            gf = clip_start_frame + lf
            prev_gf = clip_start_frame + lf - 1
            if gf >= n or prev_gf >= n:
                break
            af = bus_frames[gf]
            delta = af.amplitude - bus_frames[prev_gf].amplitude
            if (
                intensity[lf] == 0.0
                and delta > AMPLITUDE_SPIKE_DELTA
                and _passes_sensitivity(af.amplitude, sensitivity)
            ):
                _stamp_burst(
                    intensity,
                    burst_seed,
                    rgb_sign,
                    lf,
                    rng.next() * 10000.0,
                    1.0 if rng.next() >= 0.5 else -1.0,
                )

    return intensity, burst_seed, rgb_sign


def merge_burst_layers(
    procedural: tuple[np.ndarray, np.ndarray, np.ndarray],
    audio: tuple[np.ndarray, np.ndarray, np.ndarray],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per-frame max intensity; seed/sign follow the louder layer."""
    proc_i, proc_seed, proc_sign = procedural
    audio_i, audio_seed, audio_sign = audio
    intensity = np.maximum(proc_i, audio_i)
    use_audio = audio_i > proc_i
    burst_seed = np.where(use_audio, audio_seed, proc_seed)
    rgb_sign = np.where(use_audio, audio_sign, proc_sign)
    return intensity, burst_seed, rgb_sign


def precompute_signal_envelope(
    *,
    total_frames: int,
    fps: float,
    clip_start_frame: int,
    clip_id: str,
    seed: int | None,
    sensitivity: float,
    bus_select: str | None,
    bus_frames: list[AudioBusFrame] | None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    procedural = precompute_procedural_bursts(
        total_frames=total_frames,
        fps=fps,
        clip_id=clip_id,
        seed=seed,
    )
    if not (bus_select or "").strip():
        return procedural

    audio = precompute_audio_bursts(
        total_frames=total_frames,
        clip_start_frame=clip_start_frame,
        clip_id=clip_id,
        seed=seed,
        sensitivity=sensitivity,
        bus_frames=bus_frames,
    )
    return merge_burst_layers(procedural, audio)
