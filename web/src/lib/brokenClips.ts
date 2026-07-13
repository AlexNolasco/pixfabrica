/** Clip validation helpers (missing plugins, invalid params on timeline). */

import { useMemo } from 'react'
import { tKey, type TranslationKey } from '@/lib/i18n'
import { useProjectStore } from '@/store/projectStore'
import type {
  CatalogLoadStatus,
  CatalogClipItem,
  ProjectSetting,
  Track,
} from '@/store/projectStore'

export type BrokenClipRef = {
  kind: 'clip'
  trackId: string
  trackLabel: string
  clipId: string
  clipLabel: string
  clipType: string
}

export type BrokenProjectSettingRef = {
  kind: 'projectSetting'
  settingId: string
  label: string
  clipType: string
}

export type BrokenClipDiagnosticRef = BrokenClipRef | BrokenProjectSettingRef

export function catalogClipTypeSet(catalogClips: CatalogClipItem[]): Set<string> {
  return new Set(catalogClips.map((n) => n.clip_type))
}

export function isClipBroken(
  clipType: string,
  catalogLoadStatus: CatalogLoadStatus,
  availableTypes: Set<string>,
): boolean {
  if (catalogLoadStatus !== 'ready') return false
  return !availableTypes.has(clipType)
}

export function collectBrokenClips(input: {
  tracks: Track[]
  projectSettings: ProjectSetting[]
  catalogLoadStatus: CatalogLoadStatus
  catalogClips: CatalogClipItem[]
}): BrokenClipDiagnosticRef[] {
  const available = catalogClipTypeSet(input.catalogClips)
  if (input.catalogLoadStatus !== 'ready') return []

  const broken: BrokenClipDiagnosticRef[] = []
  for (const track of input.tracks) {
    for (const clip of track.clips) {
      if (isClipBroken(clip.clip_type, input.catalogLoadStatus, available)) {
        broken.push({
          kind: 'clip',
          trackId: track.id,
          trackLabel: track.label,
          clipId: clip.id,
          clipLabel: clip.label || clip.clip_type,
          clipType: clip.clip_type,
        })
      }
    }
  }
  for (const setting of input.projectSettings) {
    if (isClipBroken(setting.clip_type, input.catalogLoadStatus, available)) {
      broken.push({
        kind: 'projectSetting',
        settingId: setting.id,
        label: setting.label,
        clipType: setting.clip_type,
      })
    }
  }
  return broken
}

export function brokenClipsFingerprint(broken: BrokenClipDiagnosticRef[]): string {
  if (broken.length === 0) return ''
  return broken
    .map((item) =>
      item.kind === 'clip'
        ? `c:${item.trackId}:${item.clipId}:${item.clipType}`
        : `j:${item.settingId}:${item.clipType}`,
    )
    .sort()
    .join('|')
}

function replacePlaceholders(template: string, values: Record<string, string>): string {
  return Object.entries(values).reduce(
    (msg, [key, value]) => msg.replaceAll(`{${key}}`, value),
    template,
  )
}

export function formatBrokenClipEventMessage(item: BrokenClipRef): string {
  return replacePlaceholders(tKey('event_broken_clip'), {
    track: item.trackLabel,
    clip: item.clipLabel,
    clipType: item.clipType,
  })
}

export function formatBrokenProjectSettingEventMessage(item: BrokenProjectSettingRef): string {
  return replacePlaceholders(tKey('event_broken_project_setting'), {
    label: item.label,
    clipType: item.clipType,
  })
}

export function formatBrokenClipsSummary(count: number): string {
  return replacePlaceholders(tKey('event_broken_clips_summary'), {
    count: String(count),
  })
}

export function formatPreviewBlockedMessage(count: number): string {
  const key: TranslationKey =
    count === 1 ? 'preview_blocked_broken_clip' : 'preview_blocked_broken_clips'
  return replacePlaceholders(tKey(key), { count: String(count) })
}

let lastReportedBrokenFingerprint: string | null = null

/** Clear dedupe state (e.g. tests). */
export function resetBrokenClipDiagnostics(): void {
  lastReportedBrokenFingerprint = null
}

export function syncBrokenClipDiagnostics(
  input: {
    tracks: Track[]
    projectSettings: ProjectSetting[]
    catalogLoadStatus: CatalogLoadStatus
    catalogClips: CatalogClipItem[]
  },
  appendEventLog: (level: 'info' | 'warn' | 'error', message: string) => void,
): void {
  const broken = collectBrokenClips(input)
  const fingerprint = brokenClipsFingerprint(broken)
  if (fingerprint === lastReportedBrokenFingerprint) return
  lastReportedBrokenFingerprint = fingerprint

  if (broken.length === 0) return

  for (const item of broken) {
    appendEventLog(
      'warn',
      item.kind === 'clip'
        ? formatBrokenClipEventMessage(item)
        : formatBrokenProjectSettingEventMessage(item),
    )
  }
  if (broken.length > 1) {
    appendEventLog('warn', formatBrokenClipsSummary(broken.length))
  }
}

export function useCatalogClipTypes(): Set<string> {
  const catalogClips = useProjectStore((s) => s.catalogClips)
  return useMemo(() => catalogClipTypeSet(catalogClips), [catalogClips])
}

export function useIsClipBroken(clipType: string): boolean {
  const catalogLoadStatus = useProjectStore((s) => s.catalogLoadStatus)
  const availableTypes = useCatalogClipTypes()
  return isClipBroken(clipType, catalogLoadStatus, availableTypes)
}

export function useBrokenClipCount(): number {
  const tracks = useProjectStore((s) => s.tracks)
  const projectSettings = useProjectStore((s) => s.projectSettings)
  const catalogLoadStatus = useProjectStore((s) => s.catalogLoadStatus)
  const catalogClips = useProjectStore((s) => s.catalogClips)
  return useMemo(
    () =>
      collectBrokenClips({ tracks, projectSettings, catalogLoadStatus, catalogClips }).length,
    [tracks, projectSettings, catalogLoadStatus, catalogClips],
  )
}

export function useTrackHasBrokenClips(track: Track): boolean {
  const catalogLoadStatus = useProjectStore((s) => s.catalogLoadStatus)
  const availableTypes = useCatalogClipTypes()
  return useMemo(
    () =>
      track.clips.some((clip) =>
        isClipBroken(clip.clip_type, catalogLoadStatus, availableTypes),
      ),
    [track.clips, catalogLoadStatus, availableTypes],
  )
}
