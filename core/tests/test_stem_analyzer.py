"""StemAnalyzer rhythm + log spectrum contract."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from pixfabrica_core.audio.analysis import (
    AnalyzerKind,
    StemAnalyzer,
    load_timeline_cache,
    save_timeline_cache,
)
from pixfabrica_core.audio.bus import N_SPECTRUM, AudioBusFrame


def _drums_sample() -> Path:
    audio = Path("web/public/preview-samples/sources/drums.mp3")
    if not audio.exists():
        pytest.skip("preview sample missing")
    return audio


def _beat_count(timeline: list[AudioBusFrame]) -> int:
    return sum(1 for f in timeline if f.beat)


def _spectrum_peak_spread(timeline: list[AudioBusFrame]) -> float:
    peaks = [max(f.spectrum) for f in timeline if any(v > 0 for v in f.spectrum)]
    if not peaks:
        return 0.0
    arr = np.asarray(peaks, dtype=np.float64)
    p5, p95 = np.percentile(arr, [5, 95])
    return float(p95 - p5)


def test_stem_analyzer_emits_rhythm_flags_on_drums() -> None:
    audio = _drums_sample()
    timeline = StemAnalyzer().analyze(audio, 0.0, 8.0, 30.0)
    assert timeline
    assert _beat_count(timeline) > 0
    assert any(f.onset for f in timeline)


def test_stem_analyzer_spectrum_shape_and_range() -> None:
    audio = _drums_sample()
    timeline = StemAnalyzer().analyze(audio, 0.0, 4.0, 30.0)
    assert timeline
    frame = timeline[len(timeline) // 2]
    assert len(frame.spectrum) == N_SPECTRUM
    assert 0.0 <= max(frame.spectrum) <= 1.0
    assert _spectrum_peak_spread(timeline) > 0.05


def test_stem_analyzer_capabilities() -> None:
    caps = StemAnalyzer().capabilities()
    assert caps.beat and caps.onset and caps.percussion and caps.spectrum


def test_timeline_cache_roundtrip_v2(tmp_path: Path) -> None:
    frame = AudioBusFrame(
        spectrum=[0.1] * N_SPECTRUM,
        bass=0.5,
        mid=0.3,
        high=0.2,
        amplitude=0.4,
        beat=True,
        onset=False,
        percussion=False,
    )
    path = tmp_path / "bus.npz"
    save_timeline_cache(path, [frame])
    loaded = load_timeline_cache(path)
    assert len(loaded) == 1
    assert loaded[0].spectrum[0] == pytest.approx(0.1)
    assert loaded[0].beat is True


def test_normalize_analyzer_kind_maps_legacy() -> None:
    from pixfabrica_core.audio.analysis import normalize_analyzer_kind

    assert normalize_analyzer_kind("librosa") == AnalyzerKind.STEM
    assert normalize_analyzer_kind("fast") == AnalyzerKind.STEM


@pytest.mark.parametrize("sr", [44100, 48000])
def test_stem_analyzer_on_synthetic_tone(tmp_path: Path, sr: int) -> None:
    t = np.linspace(0.0, 0.5, int(sr * 0.5), endpoint=False, dtype=np.float32)
    wave = (0.4 * np.sin(2.0 * np.pi * 220.0 * t)).astype(np.float32)
    audio = tmp_path / "tone.wav"
    sf.write(audio, wave, sr)

    timeline = StemAnalyzer().analyze(audio, 0.0, None, 30.0)
    assert timeline
    assert any(max(f.spectrum) > 0.0 for f in timeline)
