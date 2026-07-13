import type { PexelsPhoto, PexelsVideo } from '@/lib/pexelsApi'

export interface StockProvenance {
  provider: string
  page_url: string
  creator_name: string
  creator_url?: string | null
  media_kind?: 'photo' | 'video'
  extras?: Record<string, unknown>
}

export function pexelsPhotoProvenance(photo: PexelsPhoto): StockProvenance {
  return {
    provider: 'pexels',
    page_url: photo.url,
    creator_name: photo.photographer,
    creator_url: photo.photographer_url,
    media_kind: 'photo',
  }
}

export function pexelsVideoProvenance(video: PexelsVideo): StockProvenance {
  return {
    provider: 'pexels',
    page_url: video.url,
    creator_name: video.user.name,
    creator_url: video.user.url,
    media_kind: 'video',
  }
}

export function stockAttributionParamKeys(sourceField: string): {
  attribution: string
  provider: string
} {
  return {
    attribution: `${sourceField}_attribution`,
    provider: `${sourceField}_provider`,
  }
}

export function stockAttributionParamsForField(
  sourceField: string,
  response: {
    source_attribution?: string | null
    source_provider?: string | null
  },
): Record<string, string> {
  const keys = stockAttributionParamKeys(sourceField)
  const params: Record<string, string> = {}
  if (response.source_attribution) {
    params[keys.attribution] = response.source_attribution
  }
  if (response.source_provider) {
    params[keys.provider] = response.source_provider
  }
  return params
}

export function clearedStockAttributionForField(sourceField: string): Record<string, string> {
  const keys = stockAttributionParamKeys(sourceField)
  return {
    [keys.attribution]: '',
    [keys.provider]: '',
  }
}

export function stockAttributionParams(response: {
  source_attribution?: string | null
  source_provider?: string | null
}): Record<string, string> {
  return stockAttributionParamsForField('source', response)
}

export function clearedStockAttributionParams(): Record<string, string> {
  return clearedStockAttributionForField('source')
}
