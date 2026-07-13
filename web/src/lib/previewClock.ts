import { useProjectStore } from '@/store/projectStore'

/** Live playhead while transport is running; mirrors store when paused. */
let playbackClock = 0

/** Authoritative timeline `t` for preview requests and stale-frame checks. */
export function getEffectivePreviewTime(): number {
  const { isPlaying, previewTime } = useProjectStore.getState()
  return isPlaying ? playbackClock : previewTime
}

/** Update the in-flight playhead without touching Zustand (avoids React re-renders). */
export function setPlaybackClock(t: number): void {
  playbackClock = Math.max(0, t)
}

/** Sync ref + store after pause, scrub, seek, or natural transport stop. */
export function commitPreviewTime(t: number): void {
  const clamped = Math.max(0, t)
  playbackClock = clamped
  useProjectStore.getState().setPreviewTime(clamped)
}
