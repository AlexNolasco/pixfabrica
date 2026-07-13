/** Mirrors ``pixfabrica_core.audio.sound.SoundClip`` (web editor slice). */

export type AnalyzerKind = 'stem'

export interface Sound {
  id: string
  /** Named audio bus — synced with the timeline row label. */
  bus: string
  source: string
  volume: number
  seek: number
  /** Legacy projects may still carry librosa/fast/simple — server maps to stem. */
  analyzer?: AnalyzerKind | 'librosa' | 'fast' | 'simple'
  beat_tightness: number
  start: number
  duration: number | null
  enabled: boolean
}

export const DEFAULT_ANALYZER: AnalyzerKind = 'stem'

export function soundHasRequirements(s: Pick<Sound, 'bus' | 'source'>): boolean {
  return s.bus.trim().length > 0 && s.source.trim().length > 0
}

/** Active for render when user-enabled and bus + source are set. */
export function effectiveSoundEnabled(s: Sound): boolean {
  return s.enabled && soundHasRequirements(s)
}

export function sanitizeSoundPatch(
  current: Sound,
  patch: Partial<Omit<Sound, 'id'>>,
): Sound {
  const next: Sound = { ...current, ...patch, analyzer: DEFAULT_ANALYZER }
  if (!soundHasRequirements(next)) {
    next.enabled = false
  } else if (!soundHasRequirements(current)) {
    next.enabled = true
  }
  return next
}

export function duplicateBusNames(sounds: Sound[]): Set<string> {
  const counts = new Map<string, number>()
  for (const s of sounds) {
    const name = s.bus.trim()
    if (!name) continue
    counts.set(name, (counts.get(name) ?? 0) + 1)
  }
  return new Set(
    [...counts.entries()].filter(([, count]) => count > 1).map(([name]) => name),
  )
}

export function parseAnalyzerKind(_raw: unknown): AnalyzerKind {
  return DEFAULT_ANALYZER
}
