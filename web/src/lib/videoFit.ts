export interface VideoFitParams {
  start_offset?: unknown
  playback_rate?: unknown
}

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

export interface VideoFitResult {
  duration: number
  capped: boolean
}

/** Clip length to play usable source once, capped to remaining job time. */
export function computeVideoClipFit(
  sourceDuration: number,
  params: VideoFitParams,
  trackStart: number,
  clipStart: number,
  meta: { duration: number; fps: number },
): VideoFitResult | null {
  if (!Number.isFinite(sourceDuration) || sourceDuration <= 0) return null

  const startOffset = readNonNegativeNumber(params.start_offset, 0)
  const playbackRate = readPositiveNumber(params.playback_rate, 1)
  const playable = Math.max(0, sourceDuration - startOffset)
  if (playable <= 0) return null

  const raw = playable / playbackRate
  const absoluteStart = trackStart + clipStart
  const maxFit = Math.max(1 / meta.fps, meta.duration - absoluteStart)
  const capped = raw > maxFit + 1e-9
  const duration = frameFloor(Math.min(raw, maxFit), meta.fps)
  return { duration, capped }
}
