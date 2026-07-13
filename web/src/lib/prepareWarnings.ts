import { useMemo } from 'react'
import { mediaFilenameFromSource } from '@/lib/mediaUpload'
import { tKey } from '@/lib/i18n'
import {
  clipTimelineIssue as baseClipTimelineIssue,
  type ClipTimelineIssue,
  type ProjectValidationInput,
} from '@/lib/invalidClipParams'
import {
  resetPrepareWarningDiagnostics,
  shouldLogPrepareWarnings,
} from '@/lib/prepareWarningDiagnostics'
import {
  prepareWarningsFingerprint,
  type PrepareWarningItem,
} from '@/lib/prepareWarningTypes'
import { useToastStore } from '@/store/toastStore'
import { useProjectStore, type Clip, type Track } from '@/store/projectStore'

export type { ClipTimelineIssue } from '@/lib/invalidClipParams'
export type { PrepareWarningItem } from '@/lib/prepareWarningTypes'
export { prepareWarningsFingerprint, resetPrepareWarningDiagnostics }

function replacePlaceholders(template: string, values: Record<string, string>): string {
  return Object.entries(values).reduce(
    (msg, [key, value]) => msg.replaceAll(`{${key}}`, value),
    template,
  )
}

function sourceLabel(source: string): string {
  const name = mediaFilenameFromSource(source)
  if (name) return name
  if (source.length > 80) return `${source.slice(0, 77)}…`
  return source
}

export function formatUnknownProjectVariableMessage(
  trackLabel: string,
  clipLabel: string,
  field: string,
  token: string,
): string {
  return replacePlaceholders(tKey('event_unknown_project_variable'), {
    track: trackLabel,
    clip: clipLabel,
    field,
    token,
  })
}

export function formatMissingAssetClipMessage(
  trackLabel: string,
  clipLabel: string,
  message: string,
  source: string,
): string {
  return replacePlaceholders(tKey('event_missing_asset_clip'), {
    track: trackLabel,
    clip: clipLabel,
    file: sourceLabel(source),
    detail: message,
  })
}

export function formatMissingAssetSoundMessage(bus: string, message: string, source: string): string {
  return replacePlaceholders(tKey('event_missing_asset_sound'), {
    bus,
    file: sourceLabel(source),
    detail: message,
  })
}

export function formatMissingAssetSummary(count: number): string {
  return replacePlaceholders(tKey('event_missing_asset_summary'), { count: String(count) })
}

/** Event log once per unique warning set; toast when logs panel hidden. */
export function syncPrepareWarningDiagnostics(items: PrepareWarningItem[]): void {
  if (!shouldLogPrepareWarnings(items)) return

  const state = useProjectStore.getState()
  const appendEventLog = state.appendEventLog
  const loggedSources = new Set<string>()

  for (const w of items) {
    if (w.code === 'unknown_project_variable') {
      for (const track of state.tracks) {
        const el = track.clips.find((e) => e.id === w.ref_id)
        if (!el) continue
        appendEventLog(
          'warn',
          formatUnknownProjectVariableMessage(
            track.label,
            el.label || el.clip_type,
            w.field,
            w.source,
          ),
        )
        break
      }
      continue
    }

    if (loggedSources.has(w.source)) continue
    loggedSources.add(w.source)

    if (w.kind === 'sound') {
      const sound = state.sounds.find((s) => s.id === w.ref_id)
      const bus = sound?.bus.trim() || w.ref_id
      appendEventLog('warn', formatMissingAssetSoundMessage(bus, w.message, w.source))
      continue
    }

    for (const track of state.tracks) {
      const el = track.clips.find((e) => e.id === w.ref_id)
      if (!el) continue
      appendEventLog(
        'warn',
        formatMissingAssetClipMessage(
          track.label,
          el.label || el.clip_type,
          w.message,
          w.source,
        ),
      )
      break
    }
  }

  if (items.length > 1) {
    appendEventLog('warn', formatMissingAssetSummary(items.length))
  }

  if (!state.showLogsPanel) {
    const first = items[0]!
    const toastMsg =
      items.length === 1
        ? items[0]!.code === 'unknown_project_variable'
          ? (() => {
              const first = items[0]!
              for (const track of state.tracks) {
                const el = track.clips.find((e) => e.id === first.ref_id)
                if (el) {
                  return formatUnknownProjectVariableMessage(
                    track.label,
                    el.label || el.clip_type,
                    first.field,
                    first.source,
                  )
                }
              }
              return first.message
            })()
          : first.kind === 'sound'
          ? formatMissingAssetSoundMessage(
              state.sounds.find((s) => s.id === first.ref_id)?.bus.trim() || first.ref_id,
              first.message,
              first.source,
            )
          : (() => {
              for (const track of state.tracks) {
                const el = track.clips.find((e) => e.id === first.ref_id)
                if (el) {
                  return formatMissingAssetClipMessage(
                    track.label,
                    el.label || el.clip_type,
                    first.message,
                    first.source,
                  )
                }
              }
              return first.message
            })()
        : formatMissingAssetSummary(items.length)
    useToastStore.getState().pushToast(toastMsg, 'warn')
  }
}

export function clipHasMissingAsset(
  clipId: string,
  warnings: PrepareWarningItem[],
): boolean {
  return warnings.some(
    (w) => w.kind === 'clip' && w.ref_id === clipId,
  )
}

export function clipTimelineIssueWithAssets(
  clip: Clip,
  input: ProjectValidationInput,
  warnings: PrepareWarningItem[],
): ClipTimelineIssue {
  const base = baseClipTimelineIssue(clip, input)
  if (base) return base
  if (clipHasMissingAsset(clip.id, warnings)) return 'missing_asset'
  return null
}

function useProjectValidationInput(): ProjectValidationInput {
  const tracks = useProjectStore((s) => s.tracks)
  const projectSettings = useProjectStore((s) => s.projectSettings)
  const catalogLoadStatus = useProjectStore((s) => s.catalogLoadStatus)
  const catalogClips = useProjectStore((s) => s.catalogClips)
  const catalogDetailCache = useProjectStore((s) => s.catalogDetailCache)
  const locale = useProjectStore((s) => s.appSettings.locale)
  return useMemo(
    () => ({
      tracks,
      projectSettings,
      catalogLoadStatus,
      catalogClips,
      catalogDetailCache,
      locale,
    }),
    [tracks, projectSettings, catalogLoadStatus, catalogClips, catalogDetailCache, locale],
  )
}

export function useClipTimelineIssueWithAssets(clip: Clip): ClipTimelineIssue {
  const input = useProjectValidationInput()
  const warnings = useProjectStore((s) => s.prepareWarnings)
  return useMemo(
    () => clipTimelineIssueWithAssets(clip, input, warnings),
    [clip, input, warnings],
  )
}

export function useTrackTimelineIssueWithAssets(track: Track): ClipTimelineIssue {
  const input = useProjectValidationInput()
  const warnings = useProjectStore((s) => s.prepareWarnings)
  return useMemo(() => {
    for (const clip of track.clips) {
      const issue = clipTimelineIssueWithAssets(clip, input, warnings)
      if (issue === 'broken') return 'broken'
    }
    for (const clip of track.clips) {
      if (clipTimelineIssueWithAssets(clip, input, warnings) === 'missing_asset') {
        return 'missing_asset'
      }
    }
    return null
  }, [track.clips, input, warnings])
}

export function parsePrepareWarningItems(raw: unknown): PrepareWarningItem[] {
  if (!Array.isArray(raw)) return []
  const items: PrepareWarningItem[] = []
  for (const entry of raw) {
    if (typeof entry !== 'object' || entry === null) continue
    const row = entry as Record<string, unknown>
    if (row.kind !== 'clip' && row.kind !== 'sound') continue
    if (typeof row.ref_id !== 'string') continue
    if (typeof row.source !== 'string' || !row.source.trim()) continue
    const kind = row.kind === 'sound' ? 'sound' : 'clip'
    items.push({
      kind,
      ref_id: row.ref_id,
      clip_type:
        typeof row.clip_type === 'string'
          ? row.clip_type
          : '',
      field: typeof row.field === 'string' ? row.field : 'source',
      source: row.source.trim(),
      code: typeof row.code === 'string' ? row.code : 'resolve_failed',
      message: typeof row.message === 'string' ? row.message : '',
    })
  }
  return items
}

export function applyPrepareWarningsFromPreview(raw: unknown): void {
  const items = parsePrepareWarningItems(raw)
  useProjectStore.getState().setPrepareWarnings(items)
  syncPrepareWarningDiagnostics(items)
}
