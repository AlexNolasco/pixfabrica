import {
  DEFAULT_FONT_PALETTE,
  FONT_ROLE_GROUPS,
  FONT_ROLES,
  REFERENCE_HEIGHT,
  type FontPalette,
  type FontRole,
  type FontSpec,
} from './typography.generated'

export {
  DEFAULT_FONT_PALETTE,
  FONT_ROLE_GROUPS,
  FONT_ROLES,
  REFERENCE_HEIGHT,
  type FontPalette,
  type FontRole,
  type FontSpec,
}

const MONO_ROLES = new Set<FontRole>(FONT_ROLE_GROUPS.mono)

export function cloneFontPalette(palette: FontPalette): FontPalette {
  return JSON.parse(JSON.stringify(palette)) as FontPalette
}

export function sansFamilyFromPalette(palette: FontPalette): string {
  return palette.body_medium.family
}

export function monoFamilyFromPalette(palette: FontPalette): string {
  return palette.mono_medium.family
}

/** Apply global sans/mono families; per-role weight/size unchanged. */
export function applyGlobalFamilies(
  palette: FontPalette,
  sansFamily: string,
  monoFamily: string,
): FontPalette {
  const next = cloneFontPalette(palette)
  for (const role of FONT_ROLES) {
    const spec = next[role]
    next[role] = {
      ...spec,
      family: MONO_ROLES.has(role) ? monoFamily : sansFamily,
    }
  }
  return next
}

export function unscaleFontPalette(palette: FontPalette, height: number): FontPalette {
  const factor = height / REFERENCE_HEIGHT
  if (factor === 1 || !Number.isFinite(factor) || factor <= 0) return cloneFontPalette(palette)
  const next = cloneFontPalette(palette)
  for (const role of FONT_ROLES) {
    const spec = next[role]
    next[role] = { ...spec, size: spec.size / factor }
  }
  return next
}

/** Reference-scale palette for storage; render job validator scales by height/1080. */
export function paletteForRenderJob(palette: FontPalette): FontPalette {
  return cloneFontPalette(palette)
}

export function mergeDefaultTypographySetting(
  palette: FontPalette,
  setting: { family?: string; mono_family?: string },
): FontPalette {
  const sans = setting.family?.trim()
  const mono = setting.mono_family?.trim()
  if (!sans && !mono) return cloneFontPalette(palette)
  return applyGlobalFamilies(
    palette,
    sans || sansFamilyFromPalette(palette),
    mono || monoFamilyFromPalette(palette),
  )
}

/** Capped sidebar preview size (reference sizes → panel width). */
export function previewFontSizePx(
  spec: FontSpec,
  jobWidth: number,
  panelWidth = 240,
): number {
  const scaled = spec.size * (panelWidth / Math.max(jobWidth, 1))
  const tierCap =
    spec.size >= 76 ? 28 : spec.size >= 38 ? 22 : spec.size >= 29 ? 18 : 15
  return Math.min(scaled, tierCap)
}

import type { TranslationKey } from '@/lib/i18n'

export function roleLabelKey(role: FontRole): TranslationKey {
  return `typography_role_${role}` as TranslationKey
}
