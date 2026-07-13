import { apiUploadMedia, projectUploadTarget } from '@/lib/mediaUpload'
import { fetchVideoDuration } from '@/lib/videoDurationCache'
import { computeVideoClipFit } from '@/lib/videoFit'
import { useProjectStore } from '@/store/projectStore'
import type { VisualTrackDropBatchItem } from './types'

export const VIDEO_CLIP_TYPE = 'std-video'
export const VIDEO_PLUGIN_ID = 'pixfabrica-std'

async function resolveClipLabel(): Promise<string> {
  const findLabel = () =>
    useProjectStore.getState().catalogClips.find((n) => n.clip_type === VIDEO_CLIP_TYPE)?.label

  const cached = findLabel()
  if (cached) return cached
  await useProjectStore.getState().ensureCatalogDetail(VIDEO_CLIP_TYPE)
  return findLabel() ?? 'Video Player'
}

export async function resolveVideoClipLabel(): Promise<string> {
  return resolveClipLabel()
}

export async function buildVideoParams(sourcePath: string): Promise<Record<string, unknown>> {
  const detail = await useProjectStore.getState().ensureCatalogDetail(VIDEO_CLIP_TYPE)
  return { ...(detail?.defaults ?? {}), source: sourcePath }
}

export async function buildVideoDropItem(
  file: File,
  trackLabel: string,
): Promise<VisualTrackDropBatchItem> {
  const uploaded = await apiUploadMedia(file, 'video', {
    clip_type: VIDEO_CLIP_TYPE,
    plugin_id: VIDEO_PLUGIN_ID,
  }, projectUploadTarget())
  const clipLabel = await resolveClipLabel()
  const params = await buildVideoParams(uploaded.path)
  const { meta } = useProjectStore.getState()
  const sourceDuration = await fetchVideoDuration(uploaded.path)
  const clipDuration =
    sourceDuration != null
      ? computeVideoClipFit(sourceDuration, params, 0, 0, meta)?.duration
      : undefined
  return {
    trackLabel,
    clipLabel,
    clipType: VIDEO_CLIP_TYPE,
    params,
    clipDuration,
  }
}
