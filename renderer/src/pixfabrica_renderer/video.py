from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import skia

from pixfabrica_core.video_export import (
    VideoEncoderUnavailableError,
    build_ffmpeg_video_encode_args,
    normalize_export_quality,
    normalize_video_encoder,
)


def _even(n: int) -> int:
    """Round up to even — libx264 is happiest with even width/height."""
    return (n + 1) // 2 * 2


class VideoWriter:
    """Pipes raw Skia frames to FFmpeg and encodes to mp4."""

    def __init__(
        self,
        path: Path | str,
        width: int,
        height: int,
        fps: float,
        audio_path: Path | None = None,
        *,
        export_quality: str = "master",
        video_encoder: str = "auto",
    ) -> None:
        w_even = _even(width)
        h_even = _even(height)
        quality = normalize_export_quality(export_quality)
        encoder = normalize_video_encoder(video_encoder)

        cmd: list[str] = [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "rawvideo",
            "-pixel_format",
            "bgra",  # matches Skia's kN32 color type on little-endian
            "-color_range",
            "pc",
            "-video_size",
            f"{width}x{height}",
            "-framerate",
            str(fps),
            "-i",
            "pipe:0",
        ]
        if audio_path is not None:
            cmd += ["-i", str(audio_path)]
        if w_even != width or h_even != height:
            cmd += [
                "-vf",
                f"pad={w_even}:{h_even}:(ow-iw)/2:(oh-ih)/2:color=black",
            ]
        try:
            cmd += build_ffmpeg_video_encode_args(
                export_quality=quality,
                video_encoder=encoder,
            )
        except VideoEncoderUnavailableError as exc:
            raise RuntimeError(str(exc)) from exc
        cmd += [
            "-movflags",
            "+faststart",
        ]
        if audio_path is not None:
            cmd += ["-c:a", "aac", "-shortest"]
        cmd.append(str(path))

        fd, stderr_name = tempfile.mkstemp(prefix="pixfabrica-ffmpeg-", suffix=".log", text=False)
        self._stderr_path = Path(stderr_name)
        try:
            self._proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stderr=fd,
            )
        except Exception:
            os.close(fd)
            self._stderr_path.unlink(missing_ok=True)
            raise
        os.close(fd)

        self._width = width
        self._height = height
        self._flatten_surface: skia.Surface | None = None
        self._src_pixel_buf: bytes | None = None

    def _flatten_surface_for(self, w: int, h: int) -> skia.Surface:
        flat = self._flatten_surface
        if flat is None or flat.width() != w or flat.height() != h:
            flat = skia.Surface(w, h)
            self._flatten_surface = flat
        return flat

    def _flatten_bgra(self, bgra: np.ndarray) -> memoryview:
        """Composite premultiplied BGRA onto black for video (no alpha channel in H.264)."""
        h, w = bgra.shape[0], bgra.shape[1]
        flat = self._flatten_surface_for(w, h)
        flat_canvas = flat.getCanvas()
        flat_canvas.clear(skia.ColorBLACK)
        if not bgra.flags.c_contiguous:
            bgra = np.ascontiguousarray(bgra)
        self._src_pixel_buf = bgra.tobytes()
        bitmap = skia.Bitmap()
        bitmap.installPixels(
            skia.ImageInfo.MakeN32Premul(w, h),
            self._src_pixel_buf,
            w * 4,
        )
        flat_canvas.drawBitmap(bitmap, 0, 0)
        return memoryview(flat.toarray())

    def write_frame(self, surface: skia.Surface) -> None:
        assert self._proc.stdin is not None
        self._proc.stdin.write(self._flatten_bgra(surface.toarray()))

    def write_frame_bytes(self, pixels: bytes | memoryview) -> None:
        """Write a raw BGRA frame already in the wire format (worker hot path).

        Workers compose into their own surface, dump pixels via ``surface.toarray()``,
        and ship the bytes to the parent — the parent uses this path to avoid
        rebuilding a Skia surface in-process just to read pixels back.
        """
        assert self._proc.stdin is not None
        bgra = np.frombuffer(pixels, dtype=np.uint8).reshape(self._height, self._width, 4)
        self._proc.stdin.write(self._flatten_bgra(bgra))

    def close(self) -> None:
        assert self._proc.stdin is not None
        self._proc.stdin.close()
        self._proc.wait()
        rc = self._proc.returncode if self._proc.returncode is not None else -1
        stderr_tail = ""
        path = self._stderr_path
        if path is not None:
            try:
                if path.exists():
                    raw = path.read_text(encoding="utf-8", errors="replace")
                    stderr_tail = raw[-12000:] if len(raw) > 12000 else raw
            finally:
                path.unlink(missing_ok=True)
            self._stderr_path = None
        if rc != 0:
            detail = f"FFmpeg exited with code {rc}"
            if stderr_tail.strip():
                detail = f"{detail}\n{stderr_tail.strip()}"
            raise RuntimeError(detail)

    def __enter__(self) -> VideoWriter:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
