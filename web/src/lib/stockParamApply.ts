import {
  applyPexelsPhoto,
  applyPexelsVideo,
  type PexelsOrientation,
  type PexelsPhoto,
  type PexelsVideo,
} from '@/lib/pexelsApi'
import {
  pexelsPhotoProvenance,
  pexelsVideoProvenance,
  stockAttributionParamsForField,
} from '@/lib/stockProvenance'
import type { MediaUploadContext } from '@/lib/mediaUpload'
import { useProjectStore } from '@/store/projectStore'
import type { StockParamApplyResult } from '@/store/stockPickerStore'

export type IngestStockParamResult =
  | { ok: true; result: StockParamApplyResult }
  | { ok: false; message: string }

export async function ingestStockPhotoForParam(
  photo: PexelsPhoto,
  orientation: PexelsOrientation,
  uploadContext: MediaUploadContext,
  field: string,
): Promise<IngestStockParamResult> {
  const { meta } = useProjectStore.getState()
  try {
    const uploaded = await applyPexelsPhoto(
      photo.src,
      orientation,
      meta.width,
      meta.height,
      pexelsPhotoProvenance(photo),
      { ...uploadContext, field },
    )
    return {
      ok: true,
      result: {
        path: uploaded.path,
        extraParams: stockAttributionParamsForField(field, uploaded),
      },
    }
  } catch (err) {
    return {
      ok: false,
      message: err instanceof Error ? err.message : 'Apply failed',
    }
  }
}

export async function ingestStockVideoForParam(
  video: PexelsVideo,
  uploadContext: MediaUploadContext,
  field: string,
): Promise<IngestStockParamResult> {
  const { meta } = useProjectStore.getState()
  try {
    const uploaded = await applyPexelsVideo(
      video.video_files,
      meta.width,
      meta.height,
      meta.fps,
      pexelsVideoProvenance(video),
      { ...uploadContext, field },
    )
    return {
      ok: true,
      result: {
        path: uploaded.path,
        extraParams: stockAttributionParamsForField(field, uploaded),
      },
    }
  } catch (err) {
    return {
      ok: false,
      message: err instanceof Error ? err.message : 'Apply failed',
    }
  }
}
