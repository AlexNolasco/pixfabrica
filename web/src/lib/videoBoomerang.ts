import type { VideoFitParams } from '@/lib/videoFit'

const BOOMERANG_STEM_MARKER = '.boomerang-'

/** True when the media path looks like a boomerang derivative we created. */
export function isBoomerangDerivativeSource(source: string): boolean {
  const trimmed = source.trim()
  if (!trimmed) return false
  const base = trimmed.replace(/\\/g, '/').split('/').pop() ?? trimmed
  const stem = base.replace(/\.[^.]+$/, '')
  return stem.includes(BOOMERANG_STEM_MARKER)
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

export interface VideoBoomerangPlan {
  legSourceSeconds: number
  outputDuration: number
  cycles: number
  capped: boolean
}

/** Planned boomerang output: tile forward/back cycles until job time (or compress one cycle). */
export function computeVideoBoomerangPlan(
  sourceDuration: number,
  params: VideoFitParams,
  trackStart: number,
  clipStart: number,
  meta: { duration: number; fps: number },
): VideoBoomerangPlan | null {
  if (!Number.isFinite(sourceDuration) || sourceDuration <= 0) return null

  const startOffset = readNonNegativeNumber(params.start_offset, 0)
  const playbackRate = readPositiveNumber(params.playback_rate, 1)
  const playableSource = Math.max(0, sourceDuration - startOffset)
  if (playableSource <= 0) return null

  const oneLegTimeline = playableSource / playbackRate
  const cycleTimeline = oneLegTimeline * 2
  const absoluteStart = trackStart + clipStart
  const maxDuration = Math.max(1 / meta.fps, meta.duration - absoluteStart)
  const capped = cycleTimeline > maxDuration + 1e-9

  let cycles: number
  let legTimeline: number
  let legSourceSeconds: number
  let outputDuration: number

  if (capped) {
    cycles = 1
    legTimeline = maxDuration / 2
    legSourceSeconds = Math.min(legTimeline * playbackRate, playableSource)
    outputDuration = frameFloor(maxDuration, meta.fps)
  } else {
    cycles = Math.max(1, Math.ceil(maxDuration / cycleTimeline - 1e-9))
    legTimeline = oneLegTimeline
    legSourceSeconds = playableSource
    outputDuration = frameFloor(cycles * cycleTimeline, meta.fps)
  }

  if (legSourceSeconds <= 0 || outputDuration <= 0) return null

  return { legSourceSeconds, outputDuration, cycles, capped }
}
