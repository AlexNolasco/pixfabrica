/** Theme token names (matches pixfabrica_core.theme.color.ColorToken wire values). */
export const COLOR_TOKENS = [
  'primary',
  'secondary',
  'tertiary',
  'accent',
  'background',
  'neutral',
  'neutral_variant',
] as const

export type ColorTokenName = (typeof COLOR_TOKENS)[number]

/** Default palette when job theme is not wired in the web client yet. */
export const DEFAULT_PALETTE: Record<ColorTokenName, string> = {
  primary: '#6200EE',
  secondary: '#03DAC6',
  tertiary: '#018786',
  accent: '#BB86FC',
  background: '#121212',
  neutral: '#FFFFFF',
  neutral_variant: '#E0E0E0',
}

const HEX_RE = /^#([0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/

export function isHexColor(v: unknown): v is string {
  return typeof v === 'string' && HEX_RE.test(v)
}

/** Normalize pasted or typed hex; returns null if not valid #RRGGBB or #RRGGBBAA. */
export function normalizeHexInput(raw: string): string | null {
  let s = raw.trim()
  if (!s) return null
  if (!s.startsWith('#')) s = `#${s}`
  if (!isHexColor(s)) return null
  return s.toLowerCase()
}

export function isColorToken(v: unknown): v is ColorTokenName {
  return typeof v === 'string' && (COLOR_TOKENS as readonly string[]).includes(v)
}

export function resolveSwatch(
  value: unknown,
  jobTheme: Record<string, string> | undefined,
): string {
  if (isHexColor(value)) return value
  if (isColorToken(value)) {
    const fromJob = jobTheme?.[value]
    if (fromJob && isHexColor(fromJob)) return fromJob
    return DEFAULT_PALETTE[value]
  }
  return '#888888'
}
