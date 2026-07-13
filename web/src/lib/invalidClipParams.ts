import { useMemo } from 'react'
import { listInvalidParamFields } from '@/lib/clipParamsImport'
import { tKey, type TranslationKey } from '@/lib/i18n'
import { catalogDetailCacheKey, type ClipCatalogDetail } from '@/lib/catalogDetail'
import {
  catalogClipTypeSet,
  collectBrokenClips,
  isClipBroken,
} from '@/lib/brokenClips'
import type { PrepareWarningItem } from '@/lib/prepareWarningTypes'
import { useProjectStore } from '@/store/projectStore'
import type {
  CatalogLoadStatus,
  CatalogClipItem,
  Clip,
  ProjectSetting,
  Track,
} from '@/store/projectStore'

export type InvalidParamsClipRef = {
  kind: 'clip'
  trackId: string
  trackLabel: string
  clipId: string
  clipLabel: string
  clipType: string
  invalidFields: string[]
}

export type InvalidParamsProjectSettingRef = {
  kind: 'projectSetting'
  settingId: string
  label: string
  clipType: string
  invalidFields: string[]
}

export type InvalidParamsRef = InvalidParamsClipRef | InvalidParamsProjectSettingRef

export type ClipTimelineIssue = 'broken' | 'invalid_params' | 'missing_asset' | null

export type ProjectValidationInput = {
  tracks: Track[]
  projectSettings: ProjectSetting[]
  catalogLoadStatus: CatalogLoadStatus
  catalogClips: CatalogClipItem[]
  catalogDetailCache: Record<string, ClipCatalogDetail>
  locale: string
}

function detailForClipType(
  clipType: string,
  locale: string,
  catalogDetailCache: Record<string, ClipCatalogDetail>,
): ClipCatalogDetail | undefined {
  return catalogDetailCache[catalogDetailCacheKey(clipType, locale)]
}

export function invalidFieldsForParams(
  detail: ClipCatalogDetail | undefined,
  params: Record<string, unknown>,
): string[] {
  if (!detail) return []
  return listInvalidParamFields(detail, params)
}

export function clipTimelineIssue(
  clip: Clip,
  input: ProjectValidationInput,
): ClipTimelineIssue {
  const available = catalogClipTypeSet(input.catalogClips)
  if (isClipBroken(clip.clip_type, input.catalogLoadStatus, available)) {
    return 'broken'
  }
  const detail = detailForClipType(clip.clip_type, input.locale, input.catalogDetailCache)
  if (invalidFieldsForParams(detail, clip.params).length > 0) {
    return 'invalid_params'
  }
  return null
}

export function collectProjectClipTypes(tracks: Track[], projectSettings: ProjectSetting[]): string[] {
  const types = new Set<string>()
  for (const track of tracks) {
    for (const el of track.clips) types.add(el.clip_type)
  }
  for (const setting of projectSettings) types.add(setting.clip_type)
  return [...types]
}

export function collectInvalidParams(input: ProjectValidationInput): InvalidParamsRef[] {
  if (input.catalogLoadStatus !== 'ready') return []

  const available = catalogClipTypeSet(input.catalogClips)
  const invalid: InvalidParamsRef[] = []

  for (const track of input.tracks) {
    for (const el of track.clips) {
      if (isClipBroken(el.clip_type, input.catalogLoadStatus, available)) continue
      const detail = detailForClipType(el.clip_type, input.locale, input.catalogDetailCache)
      const invalidFields = invalidFieldsForParams(detail, el.params)
      if (invalidFields.length === 0) continue
      invalid.push({
        kind: 'clip',
        trackId: track.id,
        trackLabel: track.label,
        clipId: el.id,
        clipLabel: el.label || el.clip_type,
        clipType: el.clip_type,
        invalidFields,
      })
    }
  }

  for (const setting of input.projectSettings) {
    if (isClipBroken(setting.clip_type, input.catalogLoadStatus, available)) continue
    const detail = detailForClipType(setting.clip_type, input.locale, input.catalogDetailCache)
    const invalidFields = invalidFieldsForParams(detail, setting.params)
    if (invalidFields.length === 0) continue
    invalid.push({
      kind: 'projectSetting',
      settingId: setting.id,
      label: setting.label,
      clipType: setting.clip_type,
      invalidFields,
    })
  }

  return invalid
}

export function invalidParamsFingerprint(invalid: InvalidParamsRef[]): string {
  if (invalid.length === 0) return ''
  return invalid
    .map((item) => {
      const fields = item.invalidFields.join(',')
      return item.kind === 'clip'
        ? `c:${item.trackId}:${item.clipId}:${fields}`
        : `j:${item.settingId}:${fields}`
    })
    .sort()
    .join('|')
}

function replacePlaceholders(template: string, values: Record<string, string>): string {
  return Object.entries(values).reduce(
    (msg, [key, value]) => msg.replaceAll(`{${key}}`, value),
    template,
  )
}

export function formatInvalidParamsClipEventMessage(item: InvalidParamsClipRef): string {
  return replacePlaceholders(tKey('event_invalid_params_clip'), {
    track: item.trackLabel,
    clip: item.clipLabel,
    fields: item.invalidFields.join(', '),
  })
}

export function formatInvalidParamsProjectSettingEventMessage(item: InvalidParamsProjectSettingRef): string {
  return replacePlaceholders(tKey('event_invalid_params_project_setting'), {
    label: item.label,
    fields: item.invalidFields.join(', '),
  })
}

export function formatInvalidParamsSummary(count: number): string {
  return replacePlaceholders(tKey('event_invalid_params_summary'), {
    count: String(count),
  })
}

export function formatPreviewInvalidParamsMessage(count: number): string {
  const key: TranslationKey =
    count === 1 ? 'preview_blocked_invalid_params' : 'preview_blocked_invalid_params_plural'
  return replacePlaceholders(tKey(key), { count: String(count) })
}

let lastReportedInvalidParamsFingerprint: string | null = null

export function resetInvalidParamsDiagnostics(): void {
  lastReportedInvalidParamsFingerprint = null
}

export function syncInvalidParamsDiagnostics(
  input: ProjectValidationInput,
  appendEventLog: (level: 'info' | 'warn' | 'error', message: string) => void,
): void {
  const invalid = collectInvalidParams(input)
  const fingerprint = invalidParamsFingerprint(invalid)
  if (fingerprint === lastReportedInvalidParamsFingerprint) return
  lastReportedInvalidParamsFingerprint = fingerprint

  if (invalid.length === 0) return

  for (const item of invalid) {
    appendEventLog(
      'warn',
      item.kind === 'clip'
        ? formatInvalidParamsClipEventMessage(item)
        : formatInvalidParamsProjectSettingEventMessage(item),
    )
  }
  if (invalid.length > 1) {
    appendEventLog('warn', formatInvalidParamsSummary(invalid.length))
  }
}

export function prefetchProjectClipDetails(): void {
  const state = useProjectStore.getState()
  if (state.catalogLoadStatus !== 'ready') return
  for (const clipType of collectProjectClipTypes(state.tracks, state.projectSettings)) {
    void state.ensureCatalogDetail(clipType)
  }
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

export function useInvalidParamsCount(): number {
  const input = useProjectValidationInput()
  return useMemo(() => collectInvalidParams(input).length, [input])
}

/** True when broken plugins, invalid params, or prepare-time missing assets block preview. */
export function projectHasValidationIssues(
  input: ProjectValidationInput,
  prepareWarnings: PrepareWarningItem[],
): boolean {
  if (collectBrokenClips(input).length > 0) return true
  if (collectInvalidParams(input).length > 0) return true
  if (prepareWarnings.length > 0) return true
  return false
}

export function useProjectValidationBlocked(): boolean {
  const input = useProjectValidationInput()
  const prepareWarnings = useProjectStore((s) => s.prepareWarnings)
  return useMemo(
    () => projectHasValidationIssues(input, prepareWarnings),
    [input, prepareWarnings],
  )
}

export function useClipTimelineIssue(clip: Clip): ClipTimelineIssue {
  const input = useProjectValidationInput()
  return useMemo(() => clipTimelineIssue(clip, input), [clip, input])
}

export function useTrackTimelineIssue(track: Track): ClipTimelineIssue {
  const input = useProjectValidationInput()
  return useMemo(() => {
    for (const clip of track.clips) {
      const issue = clipTimelineIssue(clip, input)
      if (issue === 'broken') return 'broken'
    }
    for (const clip of track.clips) {
      if (clipTimelineIssue(clip, input) === 'invalid_params') return 'invalid_params'
    }
    for (const clip of track.clips) {
      if (clipTimelineIssue(clip, input) === 'missing_asset') return 'missing_asset'
    }
    return null
  }, [track.clips, input])
}

export function useInvalidParamFields(
  clipType: string,
  params: Record<string, unknown>,
): string[] {
  const locale = useProjectStore((s) => s.appSettings.locale)
  const catalogDetailCache = useProjectStore((s) => s.catalogDetailCache)
  return useMemo(() => {
    const detail = catalogDetailCache[catalogDetailCacheKey(clipType, locale)]
    return invalidFieldsForParams(detail, params)
  }, [clipType, params, locale, catalogDetailCache])
}
