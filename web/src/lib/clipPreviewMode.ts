/** Isolated single-clip preview vs full composition preview in the editor. */
export type ClipPreviewMode = 'clip' | 'composition'

export function trackSupportsClipPreview(trackType?: string): boolean {
  return trackType !== 'post' && trackType !== 'audio'
}

/** Stored mode with fallback when clip preview is unavailable (e.g. post track). */
export function effectiveClipPreviewMode(
  stored: ClipPreviewMode,
  trackType?: string,
): ClipPreviewMode {
  if (stored === 'clip' && !trackSupportsClipPreview(trackType)) {
    return 'composition'
  }
  return stored
}

export function normalizeClipPreviewMode(raw: unknown): ClipPreviewMode {
  if (raw === 'composition') return 'composition'
  if (raw === 'clip' || raw === 'node') return 'clip'
  return 'clip'
}
