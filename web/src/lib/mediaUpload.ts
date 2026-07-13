import { apiFetch } from '@/lib/apiClient'
import { useProjectStore } from '@/store/projectStore'

export { mediaFilenameFromSource, mediaSourceApiPath } from '@/lib/mediaSourcePath'

const REMOTE_URL_RE = /^https?:\/\//i

export interface MediaUploadResponse {
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

export interface MediaUploadContext {
  clip_type: string
  plugin_id: string
  field?: string
}

export interface MediaUploadTarget {
  target_width: number
  target_height: number
  target_fps: number
}

export interface UploadManifestResponse {
  optimized_for?: {
    width: number
    height: number
    fps: number
  } | null
}

export interface VideoBoomerangResponse {
  path: string
  filename: string
  duration: number
  size: number
  url: string
  capped: boolean
  optimized_for?: {
    width: number
    height: number
    fps: number
  } | null
}

export interface VideoBoomerangRequest {
  source: string
  start_offset: number
  playback_rate: number
  max_duration: number
  target_fps: number
  target_width: number
  target_height: number
}

export async function apiUploadMedia(
  file: File,
  kind: string,
  context?: MediaUploadContext,
  target?: MediaUploadTarget,
): Promise<MediaUploadResponse> {
  const form = new FormData()
  form.append('file', file)
  const params = new URLSearchParams({ kind })
  appendUploadQuery(params, context, target)
  const res = await apiFetch(`/media?${params.toString()}`, { method: 'POST', body: form })
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw new Error(
      detail ? `Upload failed (${res.status}): ${detail}` : `Upload failed (${res.status})`,
    )
  }
  return res.json() as Promise<MediaUploadResponse>
}

export async function fetchUploadManifest(filename: string): Promise<UploadManifestResponse | null> {
  const safe = filename.trim()
  if (!safe) return null
  const res = await apiFetch(`/media/${encodeURIComponent(safe)}/upload-manifest`)
  if (res.status === 404) return null
  if (!res.ok) return null
  return res.json() as Promise<UploadManifestResponse>
}

export function acceptAttribute(accept: string[]): string {
  return accept.join(',')
}

export function formatMaxBytes(n: number): string {
  if (n >= 1024 * 1024) return `${Math.round(n / (1024 * 1024))} MB`
  if (n >= 1024) return `${Math.round(n / 1024)} KB`
  return `${n} B`
}

export function projectUploadTarget(): MediaUploadTarget {
  const { width, height, fps } = useProjectStore.getState().meta
  return { target_width: width, target_height: height, target_fps: fps }
}

export function isRemoteMediaUrl(value: string): boolean {
  return REMOTE_URL_RE.test(value.trim())
}

function appendUploadQuery(
  params: URLSearchParams,
  context?: MediaUploadContext,
  target?: MediaUploadTarget,
  field = 'source',
) {
  if (context) {
    params.set('clip_type', context.clip_type)
    params.set('plugin_id', context.plugin_id)
    params.set('field', field)
  }
  if (target) {
    params.set('target_width', String(target.target_width))
    params.set('target_height', String(target.target_height))
    params.set('target_fps', String(target.target_fps))
  }
}

export function projectImageUploadTarget(): Pick<MediaUploadTarget, 'target_width' | 'target_height'> {
  const { width, height } = useProjectStore.getState().meta
  return { target_width: width, target_height: height }
}

export async function apiIngestMediaUrl(
  url: string,
  kind: string,
  context: MediaUploadContext,
  target?: Pick<MediaUploadTarget, 'target_width' | 'target_height'> | MediaUploadTarget,
  field = 'source',
): Promise<MediaUploadResponse> {
  const params = new URLSearchParams({ kind, field })
  params.set('clip_type', context.clip_type)
  params.set('plugin_id', context.plugin_id)
  if (target) {
    params.set('target_width', String(target.target_width))
    params.set('target_height', String(target.target_height))
  }
  const res = await apiFetch(`/media/ingest-url?${params.toString()}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url: url.trim() }),
  })
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw new Error(
      detail ? `Ingest failed (${res.status}): ${detail}` : `Ingest failed (${res.status})`,
    )
  }
  return res.json() as Promise<MediaUploadResponse>
}

export async function apiCreateVideoBoomerang(
  body: VideoBoomerangRequest,
): Promise<VideoBoomerangResponse> {
  const res = await apiFetch('/media/video/boomerang', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw new Error(
      detail
        ? `Boomerang failed (${res.status}): ${detail}`
        : `Boomerang failed (${res.status})`,
    )
  }
  return res.json() as Promise<VideoBoomerangResponse>
}

export interface VideoReverseResponse {
  path: string
  filename: string
  duration: number
  size: number
  url: string
  optimized_for?: {
    width: number
    height: number
    fps: number
  } | null
}

export interface VideoReverseRequest {
  source: string
  start_offset: number
  playback_rate: number
  target_fps: number
  target_width: number
  target_height: number
}

export async function apiCreateVideoReverse(
  body: VideoReverseRequest,
): Promise<VideoReverseResponse> {
  const res = await apiFetch('/media/video/reverse', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw new Error(
      detail ? `Reverse failed (${res.status}): ${detail}` : `Reverse failed (${res.status})`,
    )
  }
  return res.json() as Promise<VideoReverseResponse>
}
