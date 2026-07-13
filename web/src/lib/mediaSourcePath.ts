const MEDIA_ROOT_MARKER = '/media/'

export function mediaFilenameFromSource(source: string): string {
  const trimmed = source.trim()
  if (!trimmed) return ''
  if (/^https?:\/\//i.test(trimmed)) {
    try {
      return new URL(trimmed).pathname.split('/').pop() ?? ''
    } catch {
      return ''
    }
  }
  return trimmed.replace(/\\/g, '/').split('/').pop() ?? trimmed
}

function mediaRelativeApiSegments(source: string): string[] | null {
  const normalized = source.replace(/\\/g, '/')
  const markerIndex = normalized.toLowerCase().lastIndexOf(MEDIA_ROOT_MARKER)
  if (markerIndex < 0) return null
  const rel = normalized.slice(markerIndex + MEDIA_ROOT_MARKER.length)
  if (!rel) return null
  const segments = rel.split('/').filter(Boolean)
  if (segments.some((part) => part === '.' || part === '..')) return null
  return segments
}

/** Map a stored absolute media path or http(s) URL to an ``apiFetch`` path. */
export function mediaSourceApiPath(source: string): string {
  const trimmed = source.trim()
  if (!trimmed) return ''
  if (/^https?:\/\//i.test(trimmed)) {
    try {
      return new URL(trimmed).pathname
    } catch {
      return trimmed
    }
  }
  const nested = mediaRelativeApiSegments(trimmed)
  if (nested) {
    return `/media/${nested.map(encodeURIComponent).join('/')}`
  }
  const base = mediaFilenameFromSource(trimmed)
  return `/media/${encodeURIComponent(base)}`
}
