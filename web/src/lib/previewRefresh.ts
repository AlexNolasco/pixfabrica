import { requestPreviewRefresh } from '@/lib/previewClient'
import { LIVE_PREVIEW_ENABLED } from '@/lib/previewConfig'
import { useProjectStore } from '@/store/projectStore'

const timers = new Map<string, ReturnType<typeof setTimeout>>()

function scheduleDebouncedPreviewRefresh(key: string, refresh: () => void): void {
  if (!LIVE_PREVIEW_ENABLED) return
  const ms = useProjectStore.getState().appSettings.previewDebounceMs
  const existing = timers.get(key)
  if (existing) clearTimeout(existing)
  timers.set(
    key,
    setTimeout(() => {
      timers.delete(key)
      refresh()
    }, ms),
  )
}

export function schedulePreviewRefresh(): void {
  scheduleDebouncedPreviewRefresh('preview', () => requestPreviewRefresh())
}

/** Re-prepare the warm composition session while clip preview is visible. */
export function scheduleWarmPreviewRefresh(): void {
  scheduleDebouncedPreviewRefresh('preview-warm', () => requestPreviewRefresh(true))
}

export { requestPreviewRefresh } from '@/lib/previewClient'
