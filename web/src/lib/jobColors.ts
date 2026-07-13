import type { TranslationKey } from '@/lib/i18n'
import { mediaFilenameFromSource } from '@/lib/mediaSourcePath'
import { COLOR_TOKENS, type ColorTokenName } from '@/lib/themeColor'

export type PaletteLabelTranslator = (key: TranslationKey) => string

function capitalizeToken(value: string): string {
  return value ? `${value.charAt(0).toUpperCase()}${value.slice(1)}` : value
}

function replacePlaceholders(template: string, values: Record<string, string>): string {
  return Object.entries(values).reduce(
    (msg, [key, value]) => msg.replaceAll(`{${key}}`, value),
    template,
  )
}

const EXTRACTED_FILENAME_MAX_LEN = 24

export function extractedPaletteBasename(filename: string): string {
  return mediaFilenameFromSource(filename) || filename
}

export function displayExtractedFilename(filename: string): string {
  const base = extractedPaletteBasename(filename)
  if (base.length <= EXTRACTED_FILENAME_MAX_LEN) return base
  return `${base.slice(0, EXTRACTED_FILENAME_MAX_LEN - 1)}…`
}

/** Job-level resolved palette (matches pixfabrica_core.theme.color.ColorPalette). */
export type JobColorPalette = Record<ColorTokenName, string>

export type ThemeName =
  | 'amber'
  | 'violet'
  | 'rose'
  | 'emerald'
  | 'slate'
  | 'sky'
  | 'gold'
  | 'midnight'

export type ThemeVariant = 'dark' | 'light'

export type PaletteSource =
  | { type: 'named'; theme: ThemeName; variant: ThemeVariant }
  | { type: 'extracted'; filename?: string }
  | { type: 'custom' }

/** Default named preset: Amber (Dark) — matches core NAMED_PALETTES. */
export const DEFAULT_JOB_COLORS: JobColorPalette = {
  primary: '#f1c371',
  secondary: '#f8efaf',
  tertiary: '#c99023',
  accent: '#ff9f43',
  background: '#231b10',
  neutral: '#e1dcc5',
  neutral_variant: '#8b6b40',
}

export const DEFAULT_PALETTE_SOURCE: PaletteSource = {
  type: 'named',
  theme: 'amber',
  variant: 'dark',
}

export function cloneJobColors(palette: JobColorPalette): JobColorPalette {
  return { ...palette }
}

export function presetOptionValue(theme: string, variant: string): string {
  return `${theme}/${variant}`
}

export function parsePresetOptionValue(value: string): { theme: ThemeName; variant: ThemeVariant } | null {
  const [theme, variant] = value.split('/')
  if (!theme || (variant !== 'dark' && variant !== 'light')) return null
  return { theme: theme as ThemeName, variant }
}

export function parseJobColors(raw: unknown): JobColorPalette | null {
  if (!raw || typeof raw !== 'object') return null
  const obj = raw as Record<string, unknown>
  const next = {} as JobColorPalette
  for (const key of COLOR_TOKENS) {
    const v = obj[key]
    if (typeof v !== 'string' || !/^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$/.test(v)) return null
    next[key] = v
  }
  return next
}

export function parsePaletteSource(raw: unknown): PaletteSource | null {
  if (!raw || typeof raw !== 'object') return null
  const obj = raw as Record<string, unknown>
  const type = obj.type
  if (type === 'named') {
    const theme = obj.theme
    const variant = obj.variant
    if (typeof theme !== 'string' || (variant !== 'dark' && variant !== 'light')) return null
    return { type: 'named', theme: theme as ThemeName, variant }
  }
  if (type === 'extracted') {
    const filename = obj.filename
    const raw = typeof filename === 'string' ? filename : undefined
    return {
      type: 'extracted',
      filename: raw ? extractedPaletteBasename(raw) : undefined,
    }
  }
  if (type === 'custom') return { type: 'custom' }
  return null
}

export function paletteSourceLabel(
  source: PaletteSource | null,
  t: PaletteLabelTranslator,
): string {
  if (!source) return t('left_theme_custom')
  if (source.type === 'named') {
    const variantKey = source.variant === 'dark' ? 'theme_variant_dark' : 'theme_variant_light'
    return replacePlaceholders(t('left_theme_named_preset'), {
      theme: capitalizeToken(source.theme),
      variant: t(variantKey),
    })
  }
  if (source.type === 'extracted') {
    if (!source.filename) return t('left_theme_extracted_from_image')
    return replacePlaceholders(t('left_theme_extracted_named'), {
      filename: displayExtractedFilename(source.filename),
    })
  }
  return t('left_theme_custom')
}

export function jobThemeRecord(palette: JobColorPalette): Record<string, string> {
  return palette
}
