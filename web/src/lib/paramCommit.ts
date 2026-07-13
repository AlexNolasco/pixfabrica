import { schedulePreviewRefresh } from '@/lib/previewRefresh'

const timers = new Map<string, ReturnType<typeof setTimeout>>()

const DEBOUNCE_MS = 200

export { schedulePreviewRefresh, requestPreviewRefresh } from '@/lib/previewRefresh'

export function commitClipParams(
  commitKey: string,
  immediate: boolean,
  apply: () => void,
): void {
  if (immediate) {
    const t = timers.get(commitKey)
    if (t) clearTimeout(t)
    timers.delete(commitKey)
    apply()
    schedulePreviewRefresh()
    return
  }
  const existing = timers.get(commitKey)
  if (existing) clearTimeout(existing)
  timers.set(
    commitKey,
    setTimeout(() => {
      timers.delete(commitKey)
      apply()
      schedulePreviewRefresh()
    }, DEBOUNCE_MS),
  )
}