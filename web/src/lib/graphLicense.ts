import { catalogEffectType } from '@/lib/catalogDetail'
import type { CatalogEffectItem, CatalogClipItem, Track } from '@/store/projectStore'

export function catalogLicenseIndex(
  catalogClips: CatalogClipItem[],
  catalogEffects: CatalogEffectItem[],
): Map<string, string> {
  const index = new Map<string, string>()
  for (const clip of catalogClips) {
    index.set(clip.clip_type, clip.license)
  }
  for (const effect of catalogEffects) {
    index.set(catalogEffectType(effect), effect.license)
  }
  return index
}

function collectGraphClipTypes(tracks: Track[]): string[] {
  const types: string[] = []
  for (const track of tracks) {
    if (track.enabled === false) continue
    for (const clip of track.clips) {
      if (clip.enabled === false) continue
      types.push(clip.clip_type)
      for (const effect of clip.effects ?? []) {
        if (effect.enabled === false) continue
        types.push(effect.effect_type)
      }
    }
  }
  return types
}

export function webProjectUsesExcludedLicense(
  tracks: Track[],
  catalogClips: CatalogClipItem[],
  catalogEffects: CatalogEffectItem[],
  excludedLicenses: readonly string[],
): boolean {
  if (excludedLicenses.length === 0) return false
  const excluded = new Set(excludedLicenses)
  const index = catalogLicenseIndex(catalogClips, catalogEffects)
  return collectGraphClipTypes(tracks).some((clipType) => {
    const license = index.get(clipType)
    return license != null && excluded.has(license)
  })
}

export function isLicenseUnavailableApiDetail(detail: string | undefined): boolean {
  if (!detail) return false
  if (detail.includes('license_unavailable')) return true
  try {
    const parsed = JSON.parse(detail) as { code?: string }
    return parsed.code === 'license_unavailable'
  } catch {
    return false
  }
}
