from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from pixfabrica_core.audio.bus import N_SPECTRUM, AudioBusFrame

if TYPE_CHECKING:
    from pixfabrica_core.clips.base import PrepareContext

_MAX_BPM = 220.0
_N_FFT = 2048
_SPECTRUM_FMIN_HZ = 20.0

# Legacy analyzer slugs — parsed from old projects, always routed to StemAnalyzer.
_LEGACY_ANALYZERS = frozenset({"librosa", "fast", "simple"})


class AnalyzerKind(StrEnum):
    STEM = "stem"


@dataclass(frozen=True)
class AnalyzerCapabilities:
    beat: bool
    onset: bool
    percussion: bool
    spectrum: bool


class AnalysisCancelledError(Exception):
    """Raised when a cancellation token is set mid-analysis."""


def normalize_analyzer_kind(raw: object) -> AnalyzerKind:
    """Map persisted analyzer values to the single supported backend."""
    if isinstance(raw, AnalyzerKind):
        return raw
    if isinstance(raw, str):
        value = raw.strip().lower()
        if value in _LEGACY_ANALYZERS or value == AnalyzerKind.STEM:
            return AnalyzerKind.STEM
    return AnalyzerKind.STEM


def _load_mono(path: Path, seek: float, duration: float | None) -> tuple[Any, float]:
    """Decode mono float32 audio; soundfile windowed read, librosa on failure."""
    try:
        import soundfile as sf

        info = sf.info(str(path))
        sr = float(info.samplerate)
        start_frame = max(0, int(seek * sr))
        read_frames = max(0, int(duration * sr)) if duration is not None else -1
        y, _ = sf.read(str(path), always_2d=False, start=start_frame, frames=read_frames)
        if y.ndim > 1:
            y = y.mean(axis=1)
        return y.astype("float32"), sr
    except Exception:
        import librosa

        y, sr = librosa.load(str(path), sr=None, mono=True, offset=seek, duration=duration)
        return y.astype("float32"), float(sr)


def _tightness_flux_sigma(beat_tightness: float) -> float:
    t = max(1.0, min(1000.0, beat_tightness))
    return 0.15 + (t / 1000.0) * 1.35


def _spectral_flux(spectrum: Any) -> Any:
    import numpy as np

    diff = np.diff(spectrum, axis=1, prepend=spectrum[:, :1])
    return np.maximum(0.0, diff).sum(axis=0)


def _local_peak_indices(signal: Any, threshold: float, min_gap: int) -> list[int]:
    n = len(signal)
    if n == 0:
        return []
    peaks: list[int] = []
    for i in range(n):
        left = float(signal[i - 1]) if i > 0 else float(signal[i])
        right = float(signal[i + 1]) if i < n - 1 else float(signal[i])
        if float(signal[i]) < threshold:
            continue
        if float(signal[i]) < left or float(signal[i]) < right:
            continue
        if peaks and i - peaks[-1] < min_gap:
            if float(signal[i]) > float(signal[peaks[-1]]):
                peaks[-1] = i
        else:
            peaks.append(i)
    return peaks


def _estimate_beat_period_frames(
    flux: Any,
    sr: float,
    hop: int,
    *,
    min_bpm: float = 60.0,
    max_bpm: float = _MAX_BPM,
) -> int | None:
    import numpy as np

    n = len(flux)
    if n < 8:
        return None
    min_lag = max(1, int(round((60.0 / max_bpm) * sr / hop)))
    max_lag = min(n - 1, int(round((60.0 / min_bpm) * sr / hop)))
    if max_lag <= min_lag:
        return None
    centered = flux - float(np.mean(flux))
    acf = np.correlate(centered, centered, mode="full")
    acf = acf[n - 1 :]
    segment = acf[min_lag : max_lag + 1]
    if segment.size == 0:
        return None
    return int(min_lag + int(np.argmax(segment)))


def _beat_frames_on_grid(
    flux: Any,
    period: int,
    anchor: int,
    threshold: float,
    n_frames: int,
) -> set[int]:
    tol = max(1, int(round(period * 0.125)))
    beats: set[int] = set()
    for i in range(min(n_frames, len(flux))):
        if float(flux[i]) < threshold:
            continue
        phase = (i - anchor) % period
        dist = min(phase, period - phase)
        if dist <= tol:
            beats.add(i)
    return beats


@dataclass(frozen=True)
class _RhythmFlags:
    beat: set[int]
    onset: set[int]
    percussion: set[int]


def _detect_rhythm_flags(
    power: Any,
    *,
    sr: float,
    hop: int,
    n_frames: int,
    beat_tightness: float,
    high_freq_mask: Any,
) -> _RhythmFlags:
    """Spectral-flux beat/onset/percussion on video-hop STFT power."""
    import numpy as np

    flux = _spectral_flux(power)
    high_flux = _spectral_flux(power[high_freq_mask, :]) if bool(np.any(high_freq_mask)) else flux

    sigma = _tightness_flux_sigma(beat_tightness)
    flux_std = float(np.std(flux))
    flux_med = float(np.median(flux))
    onset_threshold = flux_med + 0.35 * sigma * flux_std
    beat_threshold = flux_med + 0.55 * sigma * flux_std
    perc_threshold = float(np.median(high_flux)) + 0.4 * sigma * float(np.std(high_flux))

    min_gap = max(1, int(round((60.0 / _MAX_BPM) * sr / hop)))
    onset_peaks = _local_peak_indices(flux, onset_threshold, min_gap)
    onset_set = {i for i in onset_peaks if 0 <= i < n_frames}
    perc_peaks = _local_peak_indices(high_flux, perc_threshold, min_gap)
    percussion_set = {i for i in perc_peaks if 0 <= i < n_frames}

    period = _estimate_beat_period_frames(flux, sr, hop)
    if period and period > 0:
        import numpy as np

        anchor = onset_peaks[0] if onset_peaks else int(np.argmax(flux))
        beat_set = _beat_frames_on_grid(flux, period, anchor, beat_threshold, n_frames)
    else:
        beat_set = {
            i for i in _local_peak_indices(flux, beat_threshold, min_gap) if 0 <= i < n_frames
        }

    return _RhythmFlags(beat=beat_set, onset=onset_set, percussion=percussion_set)


def _job_wide_power_norm(power: Any) -> Any:

    g_lo = float(power.min())
    g_hi = float(power.max())
    return (power - g_lo) / max(g_hi - g_lo, 1e-8)


def _log_band_bin_edges(n_bands: int, sr: float, n_fft: int) -> Any:
    import numpy as np

    freqs = np.fft.rfftfreq(n_fft, d=1.0 / sr)
    hz_edges = np.geomspace(_SPECTRUM_FMIN_HZ, sr / 2.0, n_bands + 1)
    edges = np.searchsorted(freqs, hz_edges, side="right")
    edges[0] = 0
    edges[-1] = len(freqs)
    return edges


def _power_rows_to_log_spectrum(power_norm: Any, bin_edges: Any) -> Any:
    import numpy as np

    n_bands = len(bin_edges) - 1
    out = np.zeros((power_norm.shape[0], n_bands), dtype=np.float32)
    for band in range(n_bands):
        lo = int(bin_edges[band])
        hi = max(int(bin_edges[band + 1]), lo + 1)
        out[:, band] = power_norm[:, lo:hi].mean(axis=1)
    return out


@runtime_checkable
class AudioAnalyzerProtocol(Protocol):
    def analyze(
        self,
        path: Path,
        seek: float,
        duration: float | None,
        fps: float,
        beat_tightness: float,
        *,
        on_progress: Callable[[float], None] | None = None,
        cancel: threading.Event | None = None,
    ) -> list[AudioBusFrame]: ...

    def capabilities(self) -> AnalyzerCapabilities: ...


class StemAnalyzer:
    """HTML5-style analyzer: video-hop rFFT, log spectrum bands, flux rhythm.

    One implementation for full mixes and individual stem files — each gets its
    own named audio bus; visual clips subscribe via ``bus_select`` only.
    """

    def capabilities(self) -> AnalyzerCapabilities:
        return AnalyzerCapabilities(beat=True, onset=True, percussion=True, spectrum=True)

    def analyze(
        self,
        path: Path,
        seek: float,
        duration: float | None,
        fps: float,
        beat_tightness: float = 200.0,
        *,
        on_progress: Callable[[float], None] | None = None,
        cancel: threading.Event | None = None,
    ) -> list[AudioBusFrame]:
        import numpy as np

        if cancel and cancel.is_set():
            raise AnalysisCancelledError

        y, sr = _load_mono(path, seek, duration)

        if len(y) == 0 or fps <= 0:
            return []

        actual_duration = len(y) / float(sr)
        effective_duration = float(duration) if duration is not None else actual_duration
        if effective_duration <= 0.0:
            return []

        n_frames = int(round(effective_duration * fps))
        hop = max(1, int(round(sr / fps)))
        n_audio_frames = min(int(round(actual_duration * fps)), n_frames)
        zero = AudioBusFrame.zero()

        if n_audio_frames <= 0:
            return [zero] * n_frames

        needed_samples = (n_audio_frames - 1) * hop + hop
        y_clip = y[:needed_samples]
        if len(y_clip) < needed_samples:
            y_clip = np.pad(y_clip, (0, needed_samples - len(y_clip)))

        windows = y_clip[: n_audio_frames * hop].reshape(n_audio_frames, hop)
        amplitudes = np.sqrt(np.mean(windows**2, axis=1))

        padded = np.zeros((n_audio_frames, _N_FFT), dtype=np.float32)
        padded[:, : min(hop, _N_FFT)] = windows[:, : min(hop, _N_FFT)]
        mag = np.abs(np.fft.rfft(padded, axis=1))
        power = mag**2
        power_norm = _job_wide_power_norm(power)

        freqs = np.fft.rfftfreq(_N_FFT, d=1.0 / sr)
        bass_mask = freqs <= 250.0
        mid_mask = (freqs > 250.0) & (freqs <= 4000.0)
        high_mask = freqs > 4000.0
        bass_vals = (
            power_norm[:, bass_mask].mean(axis=1) if bass_mask.any() else np.zeros(n_audio_frames)
        )
        mid_vals = (
            power_norm[:, mid_mask].mean(axis=1) if mid_mask.any() else np.zeros(n_audio_frames)
        )
        high_vals = (
            power_norm[:, high_mask].mean(axis=1) if high_mask.any() else np.zeros(n_audio_frames)
        )

        band_edges = _log_band_bin_edges(N_SPECTRUM, sr, _N_FFT)
        spectrum_rows = _power_rows_to_log_spectrum(power_norm, band_edges)

        if on_progress:
            on_progress(0.5)
        if cancel and cancel.is_set():
            raise AnalysisCancelledError

        rhythm = _detect_rhythm_flags(
            power.T,
            sr=sr,
            hop=hop,
            n_frames=n_frames,
            beat_tightness=beat_tightness,
            high_freq_mask=high_mask,
        )

        if on_progress:
            on_progress(0.9)
        if cancel and cancel.is_set():
            raise AnalysisCancelledError

        timeline: list[AudioBusFrame] = [zero] * n_frames
        for i in range(n_audio_frames):
            timeline[i] = AudioBusFrame(
                spectrum=spectrum_rows[i].astype(np.float32).tolist(),
                bass=float(bass_vals[i]),
                mid=float(mid_vals[i]),
                high=float(high_vals[i]),
                amplitude=float(amplitudes[i]),
                beat=i in rhythm.beat,
                onset=i in rhythm.onset,
                percussion=i in rhythm.percussion,
            )

        if on_progress:
            on_progress(1.0)
        return timeline


def get_analyzer(kind: AnalyzerKind | str | None = None) -> AudioAnalyzerProtocol:
    _ = normalize_analyzer_kind(kind or AnalyzerKind.STEM)
    return StemAnalyzer()


def save_timeline_cache(path: Path, timeline: list[AudioBusFrame]) -> None:
    import numpy as np

    if not timeline:
        return
    np.savez(
        path,
        schema_version=np.array([2], dtype=np.int32),
        spectrum=np.array([f.spectrum for f in timeline], dtype=np.float32),
        bass=np.array([f.bass for f in timeline], dtype=np.float32),
        mid=np.array([f.mid for f in timeline], dtype=np.float32),
        high=np.array([f.high for f in timeline], dtype=np.float32),
        amplitude=np.array([f.amplitude for f in timeline], dtype=np.float32),
        beat=np.array([f.beat for f in timeline]),
        onset=np.array([f.onset for f in timeline]),
        percussion=np.array([f.percussion for f in timeline]),
    )


def load_timeline_cache(path: Path) -> list[AudioBusFrame]:
    import numpy as np

    with np.load(path) as data:
        if "spectrum" in data:
            n = int(data["bass"].shape[0])
            spectrum = data["spectrum"]
            bass = data["bass"]
            mid = data["mid"]
            high = data["high"]
            amplitude = data["amplitude"]
            beat = data["beat"]
            onset = data["onset"]
            percussion = data["percussion"]
            return [
                AudioBusFrame(
                    spectrum=spectrum[i].tolist(),
                    bass=float(bass[i]),
                    mid=float(mid[i]),
                    high=float(high[i]),
                    amplitude=float(amplitude[i]),
                    beat=bool(beat[i]),
                    onset=bool(onset[i]),
                    percussion=bool(percussion[i]),
                )
                for i in range(n)
            ]

        # Legacy v1 NPZ (mel freq_data) — treat as cache miss upstream; empty here.
        return []


async def _resolve_source(source: str, ctx: PrepareContext) -> Path:
    import hashlib

    import httpx

    if source.startswith(("http://", "https://")):
        cache_dir = ctx.cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)
        url_hash = hashlib.sha256(source.encode()).hexdigest()
        ext = Path(source.split("?")[0]).suffix or ".audio"
        cached = cache_dir / f"{url_hash}{ext}"
        if not cached.exists():
            tmp = cache_dir / f"{url_hash}.tmp"
            async with httpx.AsyncClient() as client:
                response = await client.get(source)
                response.raise_for_status()
                tmp.write_bytes(response.content)
            tmp.replace(cached)
        return cached

    return Path(source)
