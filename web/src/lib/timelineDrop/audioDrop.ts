import { DEFAULT_ANALYZER } from '@/lib/sound'
import type { AudioDropBatchItem } from './types'

export function buildAudioDropItem(bus: string, sourcePath: string): AudioDropBatchItem {
  return {
    bus,
    source: sourcePath,
    volume: 1,
    seek: 0,
    analyzer: DEFAULT_ANALYZER,
    beat_tightness: 200,
    start: 0,
    duration: null,
    enabled: true,
  }
}

export function uniqueBusName(stem: string, taken: Set<string>): string {
  let candidate = stem.trim() || 'Audio'
  if (!taken.has(candidate)) {
    taken.add(candidate)
    return candidate
  }
  let n = 2
  while (taken.has(`${stem} ${n}`)) n += 1
  candidate = `${stem} ${n}`
  taken.add(candidate)
  return candidate
}
