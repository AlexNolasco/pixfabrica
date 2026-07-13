import type { Sound } from '@/lib/sound'

/** Project duration to fit decoded audio (formula C, floored to frame). */
export function computeFitProjectDuration(
  bufferDuration: number,
  sound: Pick<Sound, 'start' | 'seek'>,
  fps: number,
): number {
  const raw = sound.start + bufferDuration - sound.seek
  const min = 1 / fps
  if (raw <= 0) return min
  return Math.max(min, Math.floor(raw * fps) / fps)
}
