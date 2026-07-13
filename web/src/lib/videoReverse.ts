import type { VideoFitParams } from '@/lib/videoFit'

function readPositiveNumber(value: unknown, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : fallback
}

function readNonNegativeNumber(value: unknown, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : fallback
}

function frameFloor(seconds: number, fps: number): number {
  const min = 1 / fps
  if (seconds <= 0) return min
  return Math.max(min, Math.floor(seconds * fps) / fps)
}

export interface VideoReversePlan {
  sourceSeconds: number
  outputDuration: number
}

/** Planned reversed output length after baking start offset and playback rate. */
export function computeVideoReversePlan(
  sourceDuration: number,
  params: VideoFitParams,
  meta: { fps: number },
): VideoReversePlan | null {
  if (!Number.isFinite(sourceDuration) || sourceDuration <= 0) return null

  const startOffset = readNonNegativeNumber(params.start_offset, 0)
  const playbackRate = readPositiveNumber(params.playback_rate, 1)
  const playableSource = Math.max(0, sourceDuration - startOffset)
  if (playableSource <= 0) return null

  const outputDuration = frameFloor(playableSource / playbackRate, meta.fps)
  if (outputDuration <= 0) return null

  return { sourceSeconds: playableSource, outputDuration }
}
