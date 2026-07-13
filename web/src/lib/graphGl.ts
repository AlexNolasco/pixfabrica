import { catalogEffectType } from '@/lib/catalogDetail'
import type { CatalogEffectItem, CatalogClipItem, Track } from '@/store/projectStore'

const GL_TRACK_KINDS = new Set(['gl', 'post'])
const GL_TRACK_CLIP_TYPES = new Set(['std-gl-track', 'std-post-track'])

/** Scan web store tracks for GL tracks, GL clips, or GL effects. */
export function webProjectRequiresGl(
  tracks: Track[],
  catalogClips: CatalogClipItem[],
  catalogEffects: CatalogEffectItem[],
): boolean {
  const glClipTypes = new Set(
    catalogClips.filter((clip) => clip.track_kind === 'gl').map((clip) => clip.clip_type),
  )
  const glEffectTypes = new Set(
    catalogEffects
      .filter((fx) => fx.effect_backend === 'gl')
      .map((fx) => catalogEffectType(fx)),
  )

  for (const track of tracks) {
    if (track.enabled === false) continue
    const trackType = track.trackType ?? 'skia'
    if (GL_TRACK_KINDS.has(trackType)) return true

    for (const effect of track.effects ?? []) {
      if (effect.enabled === false) continue
      if (glEffectTypes.has(effect.effect_type)) return true
    }

    for (const clip of track.clips) {
      if (clip.enabled === false) continue
      if (glClipTypes.has(clip.clip_type)) return true
      for (const effect of clip.effects ?? []) {
        if (effect.enabled === false) continue
        if (glEffectTypes.has(effect.effect_type)) return true
      }
    }
  }

  return false
}

/** Best-effort scan of raw project JSON before catalog-backed checks. */
export function rawProjectJsonRequiresGl(data: unknown): boolean {
  if (!data || typeof data !== 'object' || Array.isArray(data)) return false
  const tracks = (data as Record<string, unknown>).tracks
  if (!Array.isArray(tracks)) return false

  for (const track of tracks) {
    if (!track || typeof track !== 'object') continue
    const row = track as Record<string, unknown>
    if (row.enabled === false) continue

    const clipType = row.clip_type
    if (typeof clipType === 'string' && GL_TRACK_CLIP_TYPES.has(clipType)) return true

    const trackType = row.trackType
    if (typeof trackType === 'string' && GL_TRACK_KINDS.has(trackType.trim().toLowerCase())) {
      return true
    }
  }

  return false
}

export function isGlUnavailableApiDetail(detail: string | undefined): boolean {
  if (!detail) return false
  if (detail.includes('gl_unavailable')) return true
  try {
    const parsed = JSON.parse(detail) as { code?: string }
    return parsed.code === 'gl_unavailable'
  } catch {
    return false
  }
}
