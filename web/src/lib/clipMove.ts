import { catalogKindForTrack, trackAcceptsCatalogClips } from '@/lib/catalogDisplay'
import { canAddClipToTrack } from '@/lib/projectLimits'
import type { ServerConfig } from '@/lib/serverConfig'
import type { CatalogTrackKind, Clip, Track } from '@/store/projectStore'

const CLIP_DRAG_PREFIX = 'clip:'

export function clipDragId(trackId: string, clipId: string): string {
  return `${CLIP_DRAG_PREFIX}${trackId}:${clipId}`
}

export function parseClipDragId(id: string): { trackId: string; clipId: string } | null {
  if (!id.startsWith(CLIP_DRAG_PREFIX)) return null
  const rest = id.slice(CLIP_DRAG_PREFIX.length)
  const idx = rest.indexOf(':')
  if (idx === -1) return null
  return { trackId: rest.slice(0, idx), clipId: rest.slice(idx + 1) }
}

export function clipTrackKind(
  clipType: string,
  catalogClips: { clip_type: string; track_kind: CatalogTrackKind }[],
): CatalogTrackKind | null {
  const row = catalogClips.find((n) => n.clip_type === clipType)
  return row?.track_kind ?? null
}

export function canMoveClipToTrack(params: {
  fromTrackId: string
  clip: Clip
  destTrack: Track
  clipTrackKind: CatalogTrackKind | null
  config: Pick<ServerConfig, 'maxClipsPerTrack'>
}): boolean {
  const { fromTrackId, destTrack, clipTrackKind: kind, config } = params
  if (fromTrackId === destTrack.id) return false
  if (!destTrack.enabled) return false
  if (!trackAcceptsCatalogClips(destTrack.trackType, destTrack.enabled)) return false
  if (!kind) return false
  if (catalogKindForTrack(destTrack.trackType) !== kind) return false
  const isPost = (destTrack.trackType ?? 'skia') === 'post'
  if (isPost) return true
  return canAddClipToTrack(destTrack, config)
}
