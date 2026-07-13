import type { Sound } from '@/lib/sound'
import type { Track } from '@/store/projectStore'

export type TimelineLayoutEntry =
  | { kind: 'track'; id: string }
  | { kind: 'sound'; id: string }

export function layoutSortId(entry: TimelineLayoutEntry): string {
  return `${entry.kind}:${entry.id}`
}

export function parseLayoutSortId(id: string): TimelineLayoutEntry | null {
  const idx = id.indexOf(':')
  if (idx === -1) return null
  const kind = id.slice(0, idx)
  const entryId = id.slice(idx + 1)
  if (kind === 'track') return { kind: 'track', id: entryId }
  if (kind === 'sound') return { kind: 'sound', id: entryId }
  return null
}

/** Display order (top → bottom): front-most track first, then sounds. */
export function defaultTimelineLayout(
  tracks: Track[],
  sounds: Sound[],
): TimelineLayoutEntry[] {
  const trackEntries = [...tracks].reverse().map((t) => ({ kind: 'track' as const, id: t.id }))
  const soundEntries = sounds.map((s) => ({ kind: 'sound' as const, id: s.id }))
  return [...trackEntries, ...soundEntries]
}

export function resolveTimelineLayout(
  layout: TimelineLayoutEntry[],
  tracks: Track[],
  sounds: Sound[],
): TimelineLayoutEntry[] {
  const trackIds = new Set(tracks.map((t) => t.id))
  const soundIds = new Set(sounds.map((s) => s.id))

  const valid: TimelineLayoutEntry[] = []
  const seen = new Set<string>()

  for (const entry of layout) {
    const key = layoutSortId(entry)
    if (seen.has(key)) continue
    if (entry.kind === 'track' && trackIds.has(entry.id)) {
      valid.push(entry)
      seen.add(key)
    } else if (entry.kind === 'sound' && soundIds.has(entry.id)) {
      valid.push(entry)
      seen.add(key)
    }
  }

  for (const t of [...tracks].reverse()) {
    const key = layoutSortId({ kind: 'track', id: t.id })
    if (!seen.has(key)) {
      valid.push({ kind: 'track', id: t.id })
      seen.add(key)
    }
  }
  for (const s of sounds) {
    const key = layoutSortId({ kind: 'sound', id: s.id })
    if (!seen.has(key)) {
      valid.push({ kind: 'sound', id: s.id })
      seen.add(key)
    }
  }

  return valid
}

/** Compositor storage order (back → front) from display layout. */
export function tracksOrderFromLayout(
  layout: TimelineLayoutEntry[],
  tracks: Track[],
): Track[] {
  const byId = new Map(tracks.map((t) => [t.id, t]))
  const displayTrackIds = layout.filter((e) => e.kind === 'track').map((e) => e.id)
  const ordered = [...displayTrackIds].reverse().map((id) => byId.get(id)).filter(Boolean) as Track[]
  for (const t of tracks) {
    if (!ordered.some((o) => o.id === t.id)) ordered.unshift(t)
  }
  return ordered
}

export function soundsOrderFromLayout(
  layout: TimelineLayoutEntry[],
  sounds: Sound[],
): Sound[] {
  const byId = new Map(sounds.map((s) => [s.id, s]))
  const ordered: Sound[] = []
  for (const entry of layout) {
    if (entry.kind !== 'sound') continue
    const s = byId.get(entry.id)
    if (s) ordered.push(s)
  }
  for (const s of sounds) {
    if (!ordered.some((o) => o.id === s.id)) ordered.push(s)
  }
  return ordered
}

export function removeFromLayout(
  layout: TimelineLayoutEntry[],
  kind: TimelineLayoutEntry['kind'],
  id: string,
): TimelineLayoutEntry[] {
  return layout.filter((e) => !(e.kind === kind && e.id === id))
}
