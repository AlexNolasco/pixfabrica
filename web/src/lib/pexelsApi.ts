import { apiFetch } from '@/lib/apiClient'
import { pexelsErrorFromResponse } from '@/lib/pexelsErrors'
import type { MediaUploadContext } from '@/lib/mediaUpload'
import type { StockProvenance } from '@/lib/stockProvenance'

export type PexelsOrientation = 'landscape' | 'portrait' | 'square'

export interface PexelsPhotoSrc {
  tiny?: string | null
  small?: string | null
  medium?: string | null
  large?: string | null
  large2x?: string | null
  portrait?: string | null
  landscape?: string | null
  original?: string | null
}

export interface PexelsPhoto {
  id: number
  width: number
  height: number
  alt: string | null
  photographer: string
  photographer_url: string
  url: string
  src: PexelsPhotoSrc
}

export interface PexelsSearchResponse {
  page: number
  per_page: number
  total_results: number
  next_page: string | null
  photos: PexelsPhoto[]
}

export interface PexelsApplyResponse {
  path: string
  filename: string
  size: number
  url: string
  optimized_for?: {
    width: number
    height: number
    fps: number
  }
  source_attribution?: string | null
  source_provider?: string | null
}

export const PEXELS_PER_PAGE = 15

export function pexelsOrientationFromDimensions(width: number, height: number): PexelsOrientation {
  if (width === height) return 'square'
  return height > width ? 'portrait' : 'landscape'
}

export function pexelsPreviewUrl(photo: PexelsPhoto): string {
  return (
    photo.src.medium ??
    photo.src.small ??
    photo.src.large ??
    photo.src.portrait ??
    photo.src.landscape ??
    ''
  )
}

export async function fetchPexelsSearch(
  query: string,
  orientation: PexelsOrientation,
  page: number,
): Promise<PexelsSearchResponse> {
  const params = new URLSearchParams({
    query: query.trim(),
    orientation,
    page: String(page),
    per_page: String(PEXELS_PER_PAGE),
  })
  const res = await apiFetch(`/pexels/search?${params.toString()}`)
  if (!res.ok) {
    throw await pexelsErrorFromResponse(res.status, res)
  }
  return res.json() as Promise<PexelsSearchResponse>
}

export interface PexelsUploadContext extends MediaUploadContext {
  field: string
}

export async function applyPexelsPhoto(
  src: PexelsPhotoSrc,
  orientation: PexelsOrientation,
  targetWidth: number,
  targetHeight: number,
  provenance?: StockProvenance,
  uploadContext?: PexelsUploadContext,
): Promise<PexelsApplyResponse> {
  const res = await apiFetch('/pexels/apply', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      src,
      orientation,
      target_width: targetWidth,
      target_height: targetHeight,
      ...(provenance ? { provenance } : {}),
      ...(uploadContext
        ? {
            clip_type: uploadContext.clip_type,
            plugin_id: uploadContext.plugin_id,
            field: uploadContext.field,
          }
        : {}),
    }),
  })
  if (!res.ok) {
    throw await pexelsErrorFromResponse(res.status, res)
  }
  return res.json() as Promise<PexelsApplyResponse>
}

export interface PexelsVideoFile {
  id?: number | null
  quality?: string | null
  file_type?: string | null
  width: number
  height: number
  fps?: number | null
  size?: number | null
  link: string
}

export interface PexelsVideoUser {
  id?: number | null
  name: string
  url: string
}

export interface PexelsVideo {
  id: number
  width: number
  height: number
  duration: number
  url: string
  image: string
  user: PexelsVideoUser
  video_files: PexelsVideoFile[]
}

export interface PexelsVideoSearchResponse {
  page: number
  per_page: number
  total_results: number
  next_page: string | null
  videos: PexelsVideo[]
}

/** Smallest Pexels CDN file for in-browser hover preview (no server ingest). */
export function pexelsVideoPreviewUrl(video: PexelsVideo): string {
  const candidates = video.video_files.filter(
    (file) => file.link.trim().length > 0 && file.width > 0 && file.height > 0,
  )
  if (candidates.length === 0) return ''

  return candidates.reduce((best, file) => {
    const area = file.width * file.height
    const bestArea = best.width * best.height
    if (area !== bestArea) return area < bestArea ? file : best
    const size = file.size ?? area
    const bestSize = best.size ?? bestArea
    return size < bestSize ? file : best
  }).link
}

export async function fetchPexelsVideoSearch(
  query: string,
  orientation: PexelsOrientation,
  page: number,
): Promise<PexelsVideoSearchResponse> {
  const params = new URLSearchParams({
    query: query.trim(),
    orientation,
    page: String(page),
    per_page: String(PEXELS_PER_PAGE),
  })
  const res = await apiFetch(`/pexels/videos/search?${params.toString()}`)
  if (!res.ok) {
    throw await pexelsErrorFromResponse(res.status, res)
  }
  return res.json() as Promise<PexelsVideoSearchResponse>
}

export async function applyPexelsVideo(
  videoFiles: PexelsVideoFile[],
  targetWidth: number,
  targetHeight: number,
  targetFps: number,
  provenance?: StockProvenance,
  uploadContext?: PexelsUploadContext,
): Promise<PexelsApplyResponse> {
  const res = await apiFetch('/pexels/videos/apply', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      video_files: videoFiles,
      target_width: targetWidth,
      target_height: targetHeight,
      target_fps: targetFps,
      ...(provenance ? { provenance } : {}),
      ...(uploadContext
        ? {
            clip_type: uploadContext.clip_type,
            plugin_id: uploadContext.plugin_id,
            field: uploadContext.field,
          }
        : {}),
    }),
  })
  if (!res.ok) {
    throw await pexelsErrorFromResponse(res.status, res)
  }
  return res.json() as Promise<PexelsApplyResponse>
}
