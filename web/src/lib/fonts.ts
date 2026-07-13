import { apiGet } from '@/lib/apiClient'

export interface FontWeightEntry {
  value: number
  preview_url: string
}

export interface FontFamilyEntry {
  id: string
  family: string
  label: string
  category: 'sans' | 'mono'
  weights: FontWeightEntry[]
}

export const FALLBACK_FONT_CATALOG: FontFamilyEntry[] = [
  {
    id: 'inter',
    family: 'Inter',
    label: 'Inter',
    category: 'sans',
    weights: [
      { value: 400, preview_url: '/fonts/files/Inter-Regular.woff2' },
      { value: 500, preview_url: '/fonts/files/Inter-Medium.woff2' },
      { value: 700, preview_url: '/fonts/files/Inter-Bold.woff2' },
    ],
  },
  {
    id: 'jetbrains-mono',
    family: 'JetBrains Mono',
    label: 'JetBrains Mono',
    category: 'mono',
    weights: [{ value: 400, preview_url: '/fonts/files/JetBrainsMono-Regular.woff2' }],
  },
]

export function fontCatalogUrl(path: string, apiBase?: string): string {
  const base = apiBase ?? import.meta.env.VITE_API_BASE_URL ?? '/api'
  if (path.startsWith('http')) return path
  return `${base.replace(/\/$/, '')}${path.startsWith('/') ? path : `/${path}`}`
}

export async function fetchFontCatalog(): Promise<{
  catalog: FontFamilyEntry[]
  fromFallback: boolean
}> {
  try {
    const catalog = await apiGet<FontFamilyEntry[]>('/fonts')
    if (catalog.length === 0) {
      return { catalog: FALLBACK_FONT_CATALOG, fromFallback: true }
    }
    return { catalog, fromFallback: false }
  } catch {
    return { catalog: FALLBACK_FONT_CATALOG, fromFallback: true }
  }
}

export function findFamilyEntry(
  catalog: FontFamilyEntry[],
  family: string,
): FontFamilyEntry | undefined {
  return catalog.find((f) => f.family === family)
}

export function previewUrlForWeight(
  entry: FontFamilyEntry | undefined,
  weight: number,
  apiBase?: string,
): string | undefined {
  if (!entry) return undefined
  const match =
    entry.weights.find((w) => w.value === weight) ??
    entry.weights.reduce((best, w) =>
      Math.abs(w.value - weight) < Math.abs(best.value - weight) ? w : best,
    )
  return fontCatalogUrl(match.preview_url, apiBase)
}
