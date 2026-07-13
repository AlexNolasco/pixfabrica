import type { ClipCatalogDetail } from '@/lib/catalogDetail'

export type PreviewSampleManifest = {
  version: number
  samples: PreviewSample[]
}

export type PreviewSample = {
  id: string
  label: string
  seconds: number
  fps: number
  analyzer: string
  audio: string
  timeline: string
  sourceUrl?: string
  license?: string
}

export const DEFAULT_PREVIEW_SAMPLE_ID = 'drums'

let cached: PreviewSample[] | null = null

export async function loadPreviewSamples(): Promise<PreviewSample[]> {
  if (cached) return cached
  try {
    const res = await fetch('/preview-samples/manifest.json', { cache: 'no-cache' })
    if (!res.ok) {
      cached = []
      return cached
    }
    const data = (await res.json()) as PreviewSampleManifest
    cached = Array.isArray(data.samples) ? data.samples : []
    return cached
  } catch {
    cached = []
    return cached
  }
}

export function invalidatePreviewSamplesCache(): void {
  cached = null
}

export function pickDefaultSample(
  samples: PreviewSample[],
  currentId: string | null,
): string | null {
  if (samples.length === 0) return null
  if (currentId && samples.some((s) => s.id === currentId)) return currentId
  const drums = samples.find((s) => s.id === DEFAULT_PREVIEW_SAMPLE_ID)
  return drums?.id ?? samples[0]?.id ?? null
}

export { clipNeedsBusPreview } from '@/lib/clipBusPreview'
export type { ClipCatalogDetail }
