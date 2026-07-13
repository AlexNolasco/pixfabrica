import { apiFetch } from '@/lib/apiClient'
import { mediaSourceApiPath } from '@/lib/mediaSourcePath'

const durationCache = new Map<string, Promise<number | null>>()

const METADATA_RANGE_BYTES = 2 * 1024 * 1024

async function probeFromBlob(blob: Blob): Promise<number | null> {
  const url = URL.createObjectURL(blob)
  try {
    return await new Promise<number | null>((resolve) => {
      const video = document.createElement('video')
      video.preload = 'metadata'

      const cleanup = () => {
        video.removeAttribute('src')
        video.load()
        URL.revokeObjectURL(url)
      }

      video.addEventListener(
        'loadedmetadata',
        () => {
          const duration = video.duration
          cleanup()
          resolve(Number.isFinite(duration) && duration > 0 ? duration : null)
        },
        { once: true },
      )

      video.addEventListener(
        'error',
        () => {
          cleanup()
          resolve(null)
        },
        { once: true },
      )

      video.src = url
    })
  } catch {
    URL.revokeObjectURL(url)
    return null
  }
}

async function fetchMetadataBlob(source: string): Promise<Blob | null> {
  const fetchPath = mediaSourceApiPath(source)
  const ranged = await apiFetch(fetchPath, {
    headers: { Range: `bytes=0-${METADATA_RANGE_BYTES - 1}` },
  })
  if (ranged.ok) {
    return ranged.blob()
  }
  if (ranged.status !== 416 && ranged.status !== 404) {
    const full = await apiFetch(fetchPath)
    if (!full.ok) return null
    return full.blob()
  }
  const full = await apiFetch(fetchPath)
  if (!full.ok) return null
  return full.blob()
}

async function probeSource(source: string): Promise<number | null> {
  const blob = await fetchMetadataBlob(source)
  if (!blob) return null
  return probeFromBlob(blob)
}

/** Read container duration once per source path (shared by fit UI and import). */
export async function fetchVideoDuration(source: string): Promise<number | null> {
  const key = source.trim()
  if (!key) return null

  let pending = durationCache.get(key)
  if (!pending) {
    pending = probeSource(key)
    durationCache.set(key, pending)
  }
  try {
    return await pending
  } catch {
    durationCache.delete(key)
    return null
  }
}

export function prefetchVideoDuration(source: string): void {
  const key = source.trim()
  if (!key) return
  void fetchVideoDuration(key).catch(() => {})
}

export function invalidateVideoDuration(source: string): void {
  durationCache.delete(source.trim())
}
