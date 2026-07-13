import { apiFetch, apiGet } from '@/lib/apiClient'
import type { JobColorPalette } from '@/lib/jobColors'

export interface ThemePresetEntry {
  theme: string
  variant: 'dark' | 'light'
  label: string
  colors: JobColorPalette
}

export { FALLBACK_THEME_PRESETS } from '@/lib/themePresets.fallback'

export async function fetchThemePresets(): Promise<ThemePresetEntry[]> {
  return apiGet<ThemePresetEntry[]>('/theme/presets')
}

export async function extractPaletteFromSource(source: string): Promise<JobColorPalette> {
  const res = await apiFetch('/theme/extract', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source }),
  })
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw new Error(detail || `Palette extraction failed (${res.status})`)
  }
  return (await res.json()) as JobColorPalette
}
