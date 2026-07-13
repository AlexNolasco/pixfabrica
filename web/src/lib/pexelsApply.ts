import {
  BACKGROUND_IMAGE_CLIP_TYPE,
} from '@/lib/timelineDrop/imageDrop'
import { canAddClipToTrack, canAddTimelineRow } from '@/lib/projectLimits'
import { resolveTimelineLayout } from '@/lib/timelineLayout'
import { applyPexelsPhoto, type PexelsApplyResponse, type PexelsOrientation, type PexelsPhoto } from '@/lib/pexelsApi'
import { pexelsPhotoProvenance, stockAttributionParams } from '@/lib/stockProvenance'
import { useProjectStore, newId, type Track } from '@/store/projectStore'

export type ApplyStockPhotoResult =
  | { ok: true; trackId: string; clipId: string }
  | { ok: false; code: 'timeline_full' | 'apply_failed'; message: string }

function bottomSkiaTracksWithBackgroundImage(tracks: Track[], layout: ReturnType<typeof resolveTimelineLayout>): Track[] {
  const byId = new Map(tracks.map((t) => [t.id, t]))
  const displayTrackIds = layout.filter((e) => e.kind === 'track').map((e) => e.id)
  const matches: Track[] = []

  for (let i = displayTrackIds.length - 1; i >= 0; i -= 1) {
    const track = byId.get(displayTrackIds[i]!)
    if (!track) continue
    if ((track.trackType ?? 'skia') !== 'skia') continue
    if (track.clips.some((el) => el.clip_type === BACKGROUND_IMAGE_CLIP_TYPE)) {
      matches.push(track)
    }
  }
  return matches
}

async function resolveClipLabel(): Promise<string> {
  const findLabel = () =>
    useProjectStore
      .getState()
      .catalogClips.find((n) => n.clip_type === BACKGROUND_IMAGE_CLIP_TYPE)?.label

  const cached = findLabel()
  if (cached) return cached
  await useProjectStore.getState().ensureCatalogDetail(BACKGROUND_IMAGE_CLIP_TYPE)
  return findLabel() ?? 'Image BG'
}

async function buildImageParams(sourcePath: string): Promise<Record<string, unknown>> {
  const detail = await useProjectStore
    .getState()
    .ensureCatalogDetail(BACKGROUND_IMAGE_CLIP_TYPE)
  return { ...(detail?.defaults ?? {}), source: sourcePath }
}

function skiaTrackCount(tracks: Track[]): number {
  return tracks.filter((t) => (t.trackType ?? 'skia') === 'skia').length
}

export async function applyStockPhotoToProject(
  photo: PexelsPhoto,
  orientation: PexelsOrientation,
): Promise<ApplyStockPhotoResult> {
  const state = useProjectStore.getState()
  const { meta, tracks, sounds, timelineLayout, serverConfig } = state

  let applyPath: string
  let uploaded: PexelsApplyResponse
  try {
    uploaded = await applyPexelsPhoto(
      photo.src,
      orientation,
      meta.width,
      meta.height,
      pexelsPhotoProvenance(photo),
    )
    applyPath = uploaded.path
  } catch (err) {
    return {
      ok: false,
      code: 'apply_failed',
      message: err instanceof Error ? err.message : 'Apply failed',
    }
  }

  const clipLabel = await resolveClipLabel()
  const params = {
    ...(await buildImageParams(applyPath)),
    ...stockAttributionParams(uploaded),
  }
  const layout = resolveTimelineLayout(timelineLayout, tracks, sounds)
  const bgTracks = bottomSkiaTracksWithBackgroundImage(tracks, layout)
  const bottomBgTrack = bgTracks[0]

  if (bottomBgTrack && canAddClipToTrack(bottomBgTrack, serverConfig)) {
    const clipId = newId('el')
    state.addClip(bottomBgTrack.id, {
      id: clipId,
      clip_type: BACKGROUND_IMAGE_CLIP_TYPE,
      label: clipLabel,
      start: 0,
      duration: null,
      enabled: true,
      params,
    })
    state.select({ kind: 'clip', trackId: bottomBgTrack.id, clipId })
    return { ok: true, trackId: bottomBgTrack.id, clipId }
  }

  if (!canAddTimelineRow(tracks, sounds, serverConfig)) {
    return {
      ok: false,
      code: 'timeline_full',
      message: 'timeline_full',
    }
  }
  const trackId = newId('track')
  const clipId = newId('el')
  const skiaCount = skiaTrackCount(tracks)
  state.addTrack({
    id: trackId,
    label: `Skia Track ${skiaCount + 1}`,
    enabled: true,
    disableMode: 'bypass_compute',
    start: 0,
    duration: null,
    layout: 'fill',
    trackType: 'skia',
    clips: [
      {
        id: clipId,
        clip_type: BACKGROUND_IMAGE_CLIP_TYPE,
        label: clipLabel,
        start: 0,
        duration: null,
        enabled: true,
        params,
      },
    ],
  })
  state.select({ kind: 'clip', trackId, clipId })
  return { ok: true, trackId, clipId }
}
