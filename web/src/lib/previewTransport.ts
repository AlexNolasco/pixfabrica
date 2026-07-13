import { isCompositionPreviewActive, isClipIsolatedPreviewActive } from '@/lib/compositionPreview'
import { clipPreviewClient } from '@/lib/clipPreviewClient'
import { commitPreviewTime, getEffectivePreviewTime } from '@/lib/previewClock'
import { timelineAudioEngine } from '@/lib/timelineAudioEngine'
import { useProjectStore } from '@/store/projectStore'

const TIMELINE_IMPORT_IDLE_TIMEOUT_MS = 3000

export type PrepareTimelineImportResult =
  | { ok: true }
  | { ok: false; reason: 'preview_stop_timeout' }

/**
 * Tear down clip preview before timeline mutations (file drop, project import).
 * Switches to composition mode and waits for the clip-preview socket to go idle.
 */
export async function prepareTimelineImport(): Promise<PrepareTimelineImportResult> {
  const state = useProjectStore.getState()
  const previewState = {
    selection: state.selection,
    tracks: state.tracks,
    appSettings: state.appSettings,
  }
  if (!isClipIsolatedPreviewActive(previewState)) {
    return { ok: true }
  }

  state.setAppSettings({ clipPreviewMode: 'composition' })
  clipPreviewClient.setEnabled(false)

  const outcome = await Promise.race([
    clipPreviewClient.whenIdle().then(() => 'idle' as const),
    new Promise<'timeout'>((resolve) => {
      window.setTimeout(() => resolve('timeout'), TIMELINE_IMPORT_IDLE_TIMEOUT_MS)
    }),
  ])

  if (outcome === 'timeout') {
    return { ok: false, reason: 'preview_stop_timeout' }
  }

  return { ok: true }
}

/** Switch preview pane to composition when timeline transport takes over. */
export function exitClipPreviewForTransport(): void {
  const state = useProjectStore.getState()
  if (
    isCompositionPreviewActive({
      selection: state.selection,
      tracks: state.tracks,
      appSettings: state.appSettings,
    })
  ) {
    return
  }
  state.setAppSettings({ clipPreviewMode: 'composition' })
}

/**
 * User-initiated scrub: pause composition transport and seek to `t`.
 * No-op for transport state when already paused (still updates `previewTime`).
 */
export function pauseTransportAt(t: number): void {
  const state = useProjectStore.getState()
  const clamped = Math.max(0, t)
  if (state.isPlaying) {
    state.setIsPlaying(false)
    timelineAudioEngine.stop()
  }
  commitPreviewTime(clamped)
}

/** Enter isolated clip preview; pause timeline transport in place if running. */
export function enterClipPreviewFromToggle(): void {
  const state = useProjectStore.getState()
  if (state.isPlaying) {
    commitPreviewTime(getEffectivePreviewTime())
    state.setIsPlaying(false)
    timelineAudioEngine.stop()
  }
  state.setAppSettings({ clipPreviewMode: 'clip' })
}
