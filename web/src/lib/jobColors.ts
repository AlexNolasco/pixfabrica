import { COLOR_TOKENS, type ColorTokenName } from '@/lib/themeColor'

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
    return {
      type: 'extracted',
      filename: typeof filename === 'string' ? filename : undefined,
    }
  }
  if (type === 'custom') return { type: 'custom' }
  return null
}

export function paletteSourceLabel(source: PaletteSource | null): string {
  if (!source) return 'Custom'
  if (source.type === 'named') {
    return `${source.theme.charAt(0).toUpperCase()}${source.theme.slice(1)} (${source.variant.charAt(0).toUpperCase()}${source.variant.slice(1)})`
  }
  if (source.type === 'extracted') {
    return source.filename ? `Extracted · ${source.filename}` : 'Extracted from image'
  }
  return 'Custom'
}

export function jobThemeRecord(palette: JobColorPalette): Record<string, string> {
  return palette
}
