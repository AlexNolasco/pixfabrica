import type { ProjectMeta } from '@/store/projectStore'
import { FALLBACK_MAX_PREVIEW_LONG_SIDE } from '@/lib/serverConfig'
import { useProjectStore } from '@/store/projectStore'

function resolveMaxPreviewLongSide(override?: number): number {
  if (override !== undefined) return Math.max(1, Math.floor(override))
  return useProjectStore.getState().serverConfig.maxPreviewLongSide
}

export function previewDimensions(
  width: number,
  height: number,
  maxLongSide: number = resolveMaxPreviewLongSide(),
): { width: number; height: number } {
  const cap = Math.max(1, Math.floor(maxLongSide))
  const w = Math.max(1, Math.floor(width))
  const h = Math.max(1, Math.floor(height))
  const longSide = Math.max(w, h)
  if (longSide <= cap) return { width: w, height: h }
  const scale = cap / longSide
  return {
    width: Math.max(1, Math.floor(w * scale)),
    height: Math.max(1, Math.floor(h * scale)),
  }
}

export function previewDimensionsFromMeta(
  meta: Pick<ProjectMeta, 'width' | 'height'>,
  maxLongSide?: number,
): { width: number; height: number } {
  return previewDimensions(meta.width, meta.height, resolveMaxPreviewLongSide(maxLongSide))
}

/** @deprecated Use serverConfig.maxPreviewLongSide from the store. */
export const MAX_PREVIEW_LONG_SIDE = FALLBACK_MAX_PREVIEW_LONG_SIDE

export function previewAspectRatio(width: number, height: number): number {
  return width / height
}
