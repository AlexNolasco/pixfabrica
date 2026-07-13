import { apiUploadMedia, projectUploadTarget } from '@/lib/mediaUpload'
import { useProjectStore } from '@/store/projectStore'
import type { VisualTrackDropBatchItem } from './types'

export const BACKGROUND_IMAGE_CLIP_TYPE = 'std-background-image'
export const BACKGROUND_IMAGE_PLUGIN_ID = 'pixfabrica-std'

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

export async function buildImageDropItem(
  file: File,
  trackLabel: string,
): Promise<VisualTrackDropBatchItem> {
  const uploaded = await apiUploadMedia(file, 'image', {
    clip_type: BACKGROUND_IMAGE_CLIP_TYPE,
    plugin_id: BACKGROUND_IMAGE_PLUGIN_ID,
  }, projectUploadTarget())
  const clipLabel = await resolveClipLabel()
  const params = await buildImageParams(uploaded.path)
  return {
    trackLabel,
    clipLabel,
    clipType: BACKGROUND_IMAGE_CLIP_TYPE,
    params,
  }
}
