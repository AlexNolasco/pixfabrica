import {
  cloneJobColors,
  type JobColorPalette,
  type PaletteSource,
  type ThemeVariant,
} from '@/lib/jobColors'
import { COLOR_TOKENS, isHexColor } from '@/lib/themeColor'

const BACKGROUND_LUMINANCE_THRESHOLD = 0.45
const ANALOGOUS_OFFSET_DEG = 25

function rand(min: number, max: number): number {
  return min + Math.random() * (max - min)
}

function wrapHue(deg: number): number {
  return ((deg % 360) + 360) % 360
}

function clampByte(n: number): number {
  return Math.max(0, Math.min(255, Math.round(n)))
}

function toHex(r: number, g: number, b: number): string {
  return `#${[clampByte(r), clampByte(g), clampByte(b)]
    .map((v) => v.toString(16).padStart(2, '0'))
    .join('')}`
}

function parseHex(hex: string): { r: number; g: number; b: number } {
  const value = hex.slice(1)
  return {
    r: parseInt(value.slice(0, 2), 16),
    g: parseInt(value.slice(2, 4), 16),
    b: parseInt(value.slice(4, 6), 16),
  }
}

function rgbToHsv(r: number, g: number, b: number): { h: number; s: number; v: number } {
  const rn = r / 255
  const gn = g / 255
  const bn = b / 255
  const max = Math.max(rn, gn, bn)
  const min = Math.min(rn, gn, bn)
  const delta = max - min

  let h = 0
  if (delta !== 0) {
    if (max === rn) h = 60 * (((gn - bn) / delta) % 6)
    else if (max === gn) h = 60 * ((bn - rn) / delta + 2)
    else h = 60 * ((rn - gn) / delta + 4)
  }
  if (h < 0) h += 360

  const s = max === 0 ? 0 : delta / max
  return { h, s, v: max }
}

function hsvToRgb(h: number, s: number, v: number): { r: number; g: number; b: number } {
  const c = v * s
  const hh = h / 60
  const x = c * (1 - Math.abs((hh % 2) - 1))
  const m = v - c

  let rp = 0
  let gp = 0
  let bp = 0
  if (hh >= 0 && hh < 1) [rp, gp, bp] = [c, x, 0]
  else if (hh >= 1 && hh < 2) [rp, gp, bp] = [x, c, 0]
  else if (hh >= 2 && hh < 3) [rp, gp, bp] = [0, c, x]
  else if (hh >= 3 && hh < 4) [rp, gp, bp] = [0, x, c]
  else if (hh >= 4 && hh < 5) [rp, gp, bp] = [x, 0, c]
  else [rp, gp, bp] = [c, 0, x]

  return {
    r: (rp + m) * 255,
    g: (gp + m) * 255,
    b: (bp + m) * 255,
  }
}

function fromHsv(h: number, s: number, v: number): string {
  const { r, g, b } = hsvToRgb(wrapHue(h), s, v)
  return toHex(r, g, b)
}

/** Relative luminance (0–1), matching basic_themes._luminance. */
export function backgroundLuminance(hex: string): number {
  const { r, g, b } = parseHex(hex)
  return 0.2126 * (r / 255) + 0.7152 * (g / 255) + 0.0722 * (b / 255)
}

export function inferThemeVariant(backgroundHex: string): ThemeVariant {
  return backgroundLuminance(backgroundHex) <= BACKGROUND_LUMINANCE_THRESHOLD ? 'dark' : 'light'
}

export function resolveGenerationVariant(
  paletteSource: PaletteSource,
  colors: JobColorPalette,
): ThemeVariant {
  if (paletteSource.type === 'named') return paletteSource.variant
  return inferThemeVariant(colors.background)
}

/** Mirror pixfabrica_std.config.basic_themes._derive_accent. */
export function deriveAccentFromPrimary(primaryHex: string): string {
  const { r, g, b } = parseHex(primaryHex)
  const { h, s, v } = rgbToHsv(r, g, b)
  if (s > 0.15) return fromHsv(h + 30, s, v)
  return fromHsv(h, s, Math.min(1, v + 0.15))
}

function darkPalette(baseHue: number): JobColorPalette {
  const primary = fromHsv(baseHue, rand(0.5, 0.7), rand(0.78, 0.92))
  return {
    primary,
    secondary: fromHsv(baseHue - ANALOGOUS_OFFSET_DEG, rand(0.45, 0.65), rand(0.65, 0.82)),
    tertiary: fromHsv(baseHue + ANALOGOUS_OFFSET_DEG, rand(0.55, 0.75), rand(0.45, 0.62)),
    accent: deriveAccentFromPrimary(primary),
    background: fromHsv(baseHue, rand(0.12, 0.28), rand(0.06, 0.13)),
    neutral: fromHsv(baseHue, rand(0.08, 0.18), rand(0.88, 0.96)),
    neutral_variant: fromHsv(baseHue, rand(0.28, 0.42), rand(0.38, 0.52)),
  }
}

function lightPalette(baseHue: number): JobColorPalette {
  const primary = fromHsv(baseHue, rand(0.5, 0.72), rand(0.38, 0.52))
  return {
    primary,
    secondary: fromHsv(baseHue - ANALOGOUS_OFFSET_DEG, rand(0.45, 0.65), rand(0.48, 0.58)),
    tertiary: fromHsv(baseHue + ANALOGOUS_OFFSET_DEG, rand(0.55, 0.75), rand(0.28, 0.4)),
    accent: deriveAccentFromPrimary(primary),
    background: fromHsv(baseHue, rand(0.05, 0.18), rand(0.94, 0.99)),
    neutral: fromHsv(baseHue, rand(0.15, 0.35), rand(0.06, 0.14)),
    neutral_variant: fromHsv(baseHue, rand(0.25, 0.45), rand(0.55, 0.7)),
  }
}

export function generateJobPalette(variant: ThemeVariant): JobColorPalette {
  const baseHue = Math.random() * 360
  const palette = variant === 'dark' ? darkPalette(baseHue) : lightPalette(baseHue)
  return cloneJobColors(palette)
}

export function isValidJobPalette(palette: JobColorPalette): boolean {
  return COLOR_TOKENS.every((token) => isHexColor(palette[token]))
}
