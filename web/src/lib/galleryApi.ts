import { apiFetch, apiGet, ApiHttpError } from '@/lib/apiClient'
import type { WebProjectJson } from '@/lib/renderJob'

export interface GalleryItem {
  id: string
  category: string
  title: string
  description: string
  thumbnail_url: string
}

export interface GalleryCategory {
  id: string
  label: string
  items: GalleryItem[]
}

export interface GalleryListResponse {
  categories: GalleryCategory[]
}

export async function fetchGalleryList(): Promise<GalleryListResponse> {
  return apiGet<GalleryListResponse>('/gallery')
}

export async function fetchGalleryStarter(category: string, slug: string): Promise<unknown> {
  return apiGet<unknown>(
    `/gallery/${encodeURIComponent(category)}/${encodeURIComponent(slug)}`,
  )
}

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api'

export function galleryThumbnailSrc(category: string, slug: string): string {
  return `${API_BASE}/gallery/thumbnails/${encodeURIComponent(category)}/${encodeURIComponent(slug)}`
}

export function galleryItemKey(item: Pick<GalleryItem, 'category' | 'id'>): string {
  return `${item.category}/${item.id}`
}

export interface GalleryPublishResponse {
  category: string
  slug: string
  gallery_json: string
  thumbnail: string
  media_refs: string[]
}

export async function apiPublishToGallery(params: {
  category: string
  slug: string
  project: WebProjectJson
  thumb: File
}): Promise<GalleryPublishResponse> {
  const form = new FormData()
  form.append('category', params.category)
  form.append('slug', params.slug)
  form.append('project', JSON.stringify(params.project))
  form.append('thumb', params.thumb)
  const res = await apiFetch('/gallery/publish', { method: 'POST', body: form })
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw new ApiHttpError('POST', '/gallery/publish', res.status, detail || undefined)
  }
  return res.json() as Promise<GalleryPublishResponse>
}
