import { LIVE_PREVIEW_ENABLED, CLIP_ISOLATED_PREVIEW_ENABLED } from '@/lib/previewConfig'
import { isClipSelection } from '@/lib/selection'
import { effectiveClipPreviewMode } from '@/lib/clipPreviewMode'
import type { AppSettings, ProjectState } from '@/store/projectStore'

type CompositionPreviewState = Pick<ProjectState, 'selection' | 'tracks'> & {
  appSettings: Pick<AppSettings, 'clipPreviewMode'>
}

/** True when the preview pane shows full composition (not isolated clip preview). */
export function isCompositionPreviewActive(state: CompositionPreviewState): boolean {
  if (!LIVE_PREVIEW_ENABLED) return false
  const { selection, tracks, appSettings } = state
  if (!isClipSelection(selection)) return true
  const track = tracks.find((tr) => tr.id === selection.trackId)
  if (!track || track.trackType === 'audio') return true
  if (!CLIP_ISOLATED_PREVIEW_ENABLED) return true
  return effectiveClipPreviewMode(appSettings.clipPreviewMode, track.trackType) === 'composition'
}

/** True when the preview pane shows isolated clip preview for the selected clip. */
export function isClipIsolatedPreviewActive(state: CompositionPreviewState): boolean {
  if (!LIVE_PREVIEW_ENABLED || !CLIP_ISOLATED_PREVIEW_ENABLED) return false
  const { selection, tracks, appSettings } = state
  if (!isClipSelection(selection)) return false
  const track = tracks.find((tr) => tr.id === selection.trackId)
  if (!track || track.trackType === 'audio') return false
  return effectiveClipPreviewMode(appSettings.clipPreviewMode, track.trackType) === 'clip'
}
