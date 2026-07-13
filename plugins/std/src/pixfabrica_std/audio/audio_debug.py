from __future__ import annotations

from typing import ClassVar

import numpy as np
import skia
from pydantic import PrivateAttr

from pixfabrica_core.audio.bus import AudioBusFrame
from pixfabrica_core.audio.mixin import AudioVisualMixin
from pixfabrica_core.clips import ClipCategory, ClipSkia, ClipTag, PrepareContext, RenderContext
from pixfabrica_core.graphics import Rect


def _fit_font(text: str, base_size: float, max_width: float) -> skia.Font:
    """Return a Font at base_size, shrunk just enough so text fits max_width."""
    font = skia.Font(skia.Typeface(), base_size)
    width = font.measureText(text)
    if width > max_width and width > 0:
        font.setSize(base_size * max_width / width)
    return font


class AudioDebug(AudioVisualMixin, ClipSkia):
    """HUD overlay that visualises all audio bus signals for a frame. Dev/debug use."""

    clip_type: ClassVar[str] = "std-audio-debug"
    clip_category: ClassVar[ClipCategory] = ClipCategory.UTILITY
    clip_tags: ClassVar[list[str]] = [ClipTag.AUDIO_REACTIVE]

    # Pre-computed per-frame smoothing/BPM and event histories. Stateless
    # draw(): all temporal accumulation happens once in prepare() so that
    # parallel out-of-order frame rendering produces identical output.
    _smoothed_amp: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype="f4"))
    _amp_delta: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype="f4"))
    _inst_bpm: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype="f4"))
    _beat_gated: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype=bool))
    _raw_beat_frames: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype=np.int64))
    _gated_beat_frames: np.ndarray = PrivateAttr(
        default_factory=lambda: np.zeros(0, dtype=np.int64)
    )
    _onset_frames: np.ndarray = PrivateAttr(default_factory=lambda: np.zeros(0, dtype=np.int64))
    _percussion_frames: np.ndarray = PrivateAttr(
        default_factory=lambda: np.zeros(0, dtype=np.int64)
    )

    async def prepare(self, ctx: PrepareContext, _bounds: Rect | None = None) -> None:
        total = max(ctx.job.total_frames, 0)
        fps = float(ctx.job.fps)

        frames: list[AudioBusFrame] | None = self.bus_timeline(ctx)

        smoothed = np.zeros(total, dtype="f4")
        amp_delta = np.zeros(total, dtype="f4")
        bpm = np.zeros(total, dtype="f4")
        gated = np.zeros(total, dtype=bool)
        raw_beats: list[int] = []
        gated_beats: list[int] = []
        onsets: list[int] = []
        percussions: list[int] = []

        if total == 0 or not frames:
            self._smoothed_amp = smoothed
            self._amp_delta = amp_delta
            self._inst_bpm = bpm
            self._beat_gated = gated
            self._raw_beat_frames = np.asarray(raw_beats, dtype=np.int64)
            self._gated_beat_frames = np.asarray(gated_beats, dtype=np.int64)
            self._onset_frames = np.asarray(onsets, dtype=np.int64)
            self._percussion_frames = np.asarray(percussions, dtype=np.int64)
            return

        prev_amp = 0.0
        smoothed_acc = 0.0
        last_raw_beat_frame: int | None = None
        last_inst_bpm = 0.0

        n = min(total, len(frames))
        for f in range(n):
            a = frames[f]
            d = a.amplitude - prev_amp
            smoothed_acc = (0.90 * smoothed_acc) + (0.10 * a.amplitude)
            transient = max(0.0, d)
            prev_amp = a.amplitude

            smoothed[f] = smoothed_acc
            amp_delta[f] = d

            beat_gated = a.beat and (
                a.amplitude > (smoothed_acc * 1.20) or transient > 0.010 or a.bass > 0.14
            )
            gated[f] = beat_gated

            if a.beat:
                if last_raw_beat_frame is not None:
                    gap_frames = max(1, f - last_raw_beat_frame)
                    last_inst_bpm = (60.0 * fps) / float(gap_frames)
                last_raw_beat_frame = f
                raw_beats.append(f)
            bpm[f] = last_inst_bpm

            if beat_gated:
                gated_beats.append(f)
            if a.onset:
                onsets.append(f)
            if a.percussion:
                percussions.append(f)

        # Hold the last computed BPM through silent tail frames (matches the
        # original behaviour where _inst_bpm only updated on raw beats).
        if n < total:
            bpm[n:] = last_inst_bpm

        self._smoothed_amp = smoothed
        self._amp_delta = amp_delta
        self._inst_bpm = bpm
        self._beat_gated = gated
        self._raw_beat_frames = np.asarray(raw_beats, dtype=np.int64)
        self._gated_beat_frames = np.asarray(gated_beats, dtype=np.int64)
        self._onset_frames = np.asarray(onsets, dtype=np.int64)
        self._percussion_frames = np.asarray(percussions, dtype=np.int64)

    def draw(self, ctx: RenderContext) -> None:
        a = self.audio(ctx)
        frame = ctx.time.frame
        t = ctx.time.t
        canvas: skia.Canvas = ctx.canvas
        w = float(ctx.bounds.width)
        h = float(ctx.bounds.height)

        # Stateless lookup: history was computed in prepare()
        idx = max(0, min(frame, self._smoothed_amp.shape[0] - 1)) if self._smoothed_amp.size else 0
        amp_delta = float(self._amp_delta[idx]) if self._amp_delta.size else 0.0
        inst_bpm = float(self._inst_bpm[idx]) if self._inst_bpm.size else 0.0
        beat_gated = bool(self._beat_gated[idx]) if self._beat_gated.size else False

        if a.beat:
            flash = skia.Paint()
            flash.setARGB(60, 255, 255, 255)
            canvas.drawRect(skia.Rect.MakeWH(w, h), flash)

        if beat_gated:
            gated_flash = skia.Paint()
            gated_flash.setARGB(45, 80, 220, 255)
            canvas.drawRect(skia.Rect.MakeWH(w, h), gated_flash)

        if a.onset:
            onset_flash = skia.Paint()
            onset_flash.setARGB(40, 255, 220, 0)
            canvas.drawRect(skia.Rect.MakeWH(w, h), onset_flash)

        if a.percussion:
            perc_flash = skia.Paint()
            perc_flash.setARGB(40, 255, 120, 0)
            canvas.drawRect(skia.Rect.MakeWH(w, h), perc_flash)

        bar_w = w / 3.0
        for i, (val, r, g, b) in enumerate(
            [(a.bass, 220, 60, 60), (a.mid, 60, 200, 60), (a.high, 60, 100, 220)]
        ):
            bar_h = val * h * 0.45
            bx = i * bar_w + 4
            by = h - bar_h
            p = skia.Paint(AntiAlias=True)
            p.setARGB(200, r, g, b)
            canvas.drawRect(skia.Rect.MakeXYWH(bx, by, bar_w - 8, bar_h), p)

        radius = max(8.0, a.amplitude * min(w, h) * 0.35)
        ring = skia.Paint(AntiAlias=True)
        ring.setStyle(skia.Paint.kStroke_Style)
        if a.onset:
            ring.setARGB(255, 255, 220, 0)
            ring.setStrokeWidth(5.0)
        else:
            ring.setARGB(220, 255, 255, 255)
            ring.setStrokeWidth(3.0)
        canvas.drawCircle(w / 2.0, h / 2.0, radius, ring)

        hud_paint = skia.Paint(Color=skia.ColorWHITE)
        hud = (
            f"f={frame:05d} t={t:7.3f}s  "
            f"raw={'Y' if a.beat else 'N'}  gated={'Y' if beat_gated else 'N'}  "
            f"bpm~{inst_bpm:6.1f}  amp={a.amplitude:.3f}  d_amp={amp_delta:+.3f}"
        )
        hud_font = _fit_font(hud, 18.0, w - 20.0)
        canvas.drawString(hud, 10.0, 66.0, hud_font, hud_paint)

        lane_h = 16.0
        lane_gap = 8.0
        raw_lane_y = h - (lane_h * 4 + lane_gap * 3 + 16.0)
        gated_lane_y = raw_lane_y + lane_h + lane_gap
        onset_lane_y = gated_lane_y + lane_h + lane_gap
        perc_lane_y = onset_lane_y + lane_h + lane_gap
        lane_bg = skia.Paint()
        lane_bg.setARGB(120, 20, 20, 20)
        canvas.drawRect(skia.Rect.MakeXYWH(8.0, raw_lane_y, w - 16.0, lane_h), lane_bg)
        canvas.drawRect(skia.Rect.MakeXYWH(8.0, gated_lane_y, w - 16.0, lane_h), lane_bg)
        canvas.drawRect(skia.Rect.MakeXYWH(8.0, onset_lane_y, w - 16.0, lane_h), lane_bg)
        canvas.drawRect(skia.Rect.MakeXYWH(8.0, perc_lane_y, w - 16.0, lane_h), lane_bg)

        ppf = 2.0
        raw_tick = skia.Paint()
        raw_tick.setARGB(255, 255, 80, 80)
        raw_tick.setStrokeWidth(2.0)
        gated_tick = skia.Paint()
        gated_tick.setARGB(255, 80, 220, 255)
        gated_tick.setStrokeWidth(2.0)
        onset_tick = skia.Paint()
        onset_tick.setARGB(255, 255, 220, 0)
        onset_tick.setStrokeWidth(2.0)
        perc_tick = skia.Paint()
        perc_tick.setARGB(255, 255, 120, 0)
        perc_tick.setStrokeWidth(2.0)

        x_now = w - 8.0
        x_min = 8.0
        # Maximum frame distance still visible in the lane
        max_age = int((x_now - x_min) / ppf) + 1

        def _draw_lane(events: np.ndarray, lane_y: float, paint: skia.Paint) -> None:
            if events.size == 0:
                return
            # bisect_right(frame) — count of events with frame_index <= frame
            upper = int(np.searchsorted(events, frame, side="right"))
            lower_frame = frame - max_age
            lower = int(np.searchsorted(events, lower_frame, side="left"))
            for k in range(upper - 1, lower - 1, -1):
                ev = int(events[k])
                x = x_now - ((frame - ev) * ppf)
                canvas.drawLine(x, lane_y, x, lane_y + lane_h, paint)

        _draw_lane(self._raw_beat_frames, raw_lane_y, raw_tick)
        _draw_lane(self._gated_beat_frames, gated_lane_y, gated_tick)
        _draw_lane(self._onset_frames, onset_lane_y, onset_tick)
        _draw_lane(self._percussion_frames, perc_lane_y, perc_tick)

        lane_label_font = skia.Font(skia.Typeface(), 14.0)
        lane_label_paint = skia.Paint(Color=skia.ColorWHITE)
        canvas.drawString("raw beats", 12.0, raw_lane_y - 3.0, lane_label_font, lane_label_paint)
        canvas.drawString(
            "gated beats", 12.0, gated_lane_y - 3.0, lane_label_font, lane_label_paint
        )
        canvas.drawString("onsets", 12.0, onset_lane_y - 3.0, lane_label_font, lane_label_paint)
        canvas.drawString("percussion", 12.0, perc_lane_y - 3.0, lane_label_font, lane_label_paint)

        tp = skia.Paint(Color=skia.ColorWHITE)
        line = (
            f"bass={a.bass:.2f}  mid={a.mid:.2f}  high={a.high:.2f}"
            f"  amp={a.amplitude:.3f}  beat={'Y' if a.beat else 'N'}"
            f"  onset={'Y' if a.onset else 'N'}  perc={'Y' if a.percussion else 'N'}"
        )
        font = _fit_font(line, 24.0, w - 20.0)
        canvas.drawString(line, 10.0, 40.0, font, tp)
