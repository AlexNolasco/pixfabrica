"""Mix SoundClip audio files into a single WAV for FFmpeg muxing."""

from __future__ import annotations

from pathlib import Path

from pixfabrica_core.audio.sound import SoundClip

SAMPLE_RATE = 44100


def mix_sounds(
    sounds: list[SoundClip],
    total_duration: float,
    out_path: Path,
) -> Path | None:
    """Mix all prepared SoundClips into a single WAV at out_path.

    Honors each sound's start, seek, duration, and volume.
    Returns out_path on success, None if there are no active sounds.
    """
    import librosa
    import numpy as np
    import soundfile as sf

    active = [
        s for s in sounds if s.enabled and s.bus.strip() and s.is_ready and s.local_path is not None
    ]
    if not active:
        return None

    total_samples = int(total_duration * SAMPLE_RATE)
    mixed = np.zeros(total_samples, dtype=np.float32)

    for sound in active:
        assert sound.local_path is not None
        y, _ = librosa.load(
            str(sound.local_path),
            sr=SAMPLE_RATE,
            mono=True,
            offset=sound.seek,
            duration=sound.duration,
        )
        y = (y * sound.volume).astype(np.float32)

        start_sample = int(sound.start * SAMPLE_RATE)
        end_sample = min(start_sample + len(y), total_samples)
        copy_len = end_sample - start_sample
        if copy_len > 0:
            mixed[start_sample:end_sample] += y[:copy_len]

    # Peak-normalize to prevent clipping when sounds overlap
    peak = float(np.abs(mixed).max())
    if peak > 1.0:
        mixed /= peak

    sf.write(str(out_path), mixed, SAMPLE_RATE)
    return out_path
