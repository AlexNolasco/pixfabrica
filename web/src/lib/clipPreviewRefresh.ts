import { requestClipPreviewFromStore } from '@/lib/clipPreviewClient'
import { CLIP_ISOLATED_PREVIEW_ENABLED } from '@/lib/previewConfig'
import { useProjectStore } from '@/store/projectStore'

let debounceTimer: ReturnType<typeof setTimeout> | null = null

/** Debounced isolated clip preview at local time `t` (seconds). */
export function scheduleClipPreviewRefresh(t: number, loopSeconds: number): void {
  if (!CLIP_ISOLATED_PREVIEW_ENABLED) return
  if (debounceTimer) clearTimeout(debounceTimer)
  const ms = useProjectStore.getState().appSettings.previewDebounceMs
  debounceTimer = setTimeout(() => {
    debounceTimer = null
    requestClipPreviewFromStore(t, loopSeconds)
  }, ms)
}

export function flushClipPreviewRefresh(t: number, loopSeconds: number): void {
  if (!CLIP_ISOLATED_PREVIEW_ENABLED) return
  if (debounceTimer) {
    clearTimeout(debounceTimer)
    debounceTimer = null
  }
  requestClipPreviewFromStore(t, loopSeconds)
}
