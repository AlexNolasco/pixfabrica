import { canAddTimelineRow } from '@/lib/projectLimits'
import { applyPexelsVideo, type PexelsApplyResponse, type PexelsVideo } from '@/lib/pexelsApi'
import { pexelsVideoProvenance, stockAttributionParams } from '@/lib/stockProvenance'
import { tKey } from '@/lib/i18n'
import { computeVideoClipFit } from '@/lib/videoFit'
import {
  VIDEO_CLIP_TYPE,
  buildVideoParams,
  resolveVideoClipLabel,
} from '@/lib/timelineDrop/videoDrop'
import { useProjectStore } from '@/store/projectStore'

export type ApplyStockVideoResult =
  | { ok: true; trackId: string; clipId: string }
  | { ok: false; code: 'timeline_full' | 'apply_failed'; message: string }

export async function applyStockVideoToProject(video: PexelsVideo): Promise<ApplyStockVideoResult> {
  const state = useProjectStore.getState()
  const { meta, tracks, sounds, serverConfig } = state

  if (!canAddTimelineRow(tracks, sounds, serverConfig)) {
    return {
      ok: false,
      code: 'timeline_full',
      message: 'timeline_full',
    }
  }

  let applyPath: string
  let uploaded: PexelsApplyResponse
  try {
    uploaded = await applyPexelsVideo(
      video.video_files,
      meta.width,
      meta.height,
      meta.fps,
      pexelsVideoProvenance(video),
    )
    applyPath = uploaded.path
  } catch (err) {
    return {
      ok: false,
      code: 'apply_failed',
      message: err instanceof Error ? err.message : 'Apply failed',
    }
  }

  const clipLabel = await resolveVideoClipLabel()
  const params = {
    ...(await buildVideoParams(applyPath)),
    ...stockAttributionParams(uploaded),
  }
  const loop = video.duration > 0 && video.duration < meta.duration
  params.loop = loop

  const clipDuration =
    video.duration > 0
      ? computeVideoClipFit(video.duration, params, 0, 0, meta)?.duration
      : undefined

  const trackLabel = tKey('stock_video_track_label').replace('{name}', video.user.name)

  const placed = state.applyTimelineImportBatch({
    visualTracks: [
      {
        trackLabel,
        clipLabel,
        clipType: VIDEO_CLIP_TYPE,
        params,
        clipDuration,
      },
    ],
    sounds: [],
    layoutOrder: [{ kind: 'track', trackIndex: 0 }],
  })

  if (!placed?.frontTrackId || !placed.frontClipId) {
    return {
      ok: false,
      code: 'timeline_full',
      message: 'timeline_full',
    }
  }

  return {
    ok: true,
    trackId: placed.frontTrackId,
    clipId: placed.frontClipId,
  }
}
