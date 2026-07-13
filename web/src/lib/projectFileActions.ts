import type { TranslationKey } from '@/lib/i18n'
import { stopPlaybackOnApiLoss } from '@/lib/playbackOnApiLoss'
import {
  apiExportProjectBundle,
  apiImportProjectBundle,
  isBundleExportMissingError,
} from '@/lib/projectBundle'
import {
  isGlUnavailableApiDetail,
  rawProjectJsonRequiresGl,
  webProjectRequiresGl,
} from '@/lib/graphGl'
import { webProjectUsesExcludedLicense } from '@/lib/graphLicense'
import { fromWebProjectJson, toRenderJob, toWebProjectJson, type WebProjectJson } from '@/lib/renderJob'
import { useProjectStore } from '@/store/projectStore'

const INVALID_FILENAME_CHARS = /[\\/:*?"<>|]/g

export type ProjectImportPayload = ReturnType<typeof fromWebProjectJson>

export type ProjectImportParseResult =
  | { ok: true; payload: ProjectImportPayload; filename: string }
  | { ok: false; filename: string; messageKey: TranslationKey }

/** Derive a safe `.json` download name from the project title. */
export function exportFilenameFromTitle(title: string): string {
  const trimmed = title.trim()
  const base = trimmed.length > 0 ? trimmed : 'untitled'
  const safe = base.replace(INVALID_FILENAME_CHARS, '').trim()
  return `${safe.length > 0 ? safe : 'untitled'}.json`
}

export function projectHasTimelineContent(): boolean {
  const { tracks, sounds } = useProjectStore.getState()
  return tracks.length > 0 || sounds.length > 0
}

export function executeNewProject(): void {
  stopPlaybackOnApiLoss()
  const state = useProjectStore.getState()
  state.setSettingsPanelOpen(false)
  state.resetProject()
}

function looksLikeProjectJson(data: unknown): data is WebProjectJson {
  if (typeof data !== 'object' || data === null || Array.isArray(data)) return false
  const record = data as Record<string, unknown>
  return (
    'tracks' in record ||
    'sounds' in record ||
    'width' in record ||
    'height' in record ||
    'fps' in record ||
    'duration' in record ||
    'title' in record
  )
}

export function parseProjectJsonText(text: string, filename: string): ProjectImportParseResult {
  let data: unknown
  try {
    data = JSON.parse(text)
  } catch {
    return { ok: false, filename, messageKey: 'file_import_invalid' }
  }
  return parseProjectJsonValue(data, filename)
}

export function parseProjectJsonValue(data: unknown, filename: string): ProjectImportParseResult {
  if (!looksLikeProjectJson(data)) {
    return { ok: false, filename, messageKey: 'file_import_invalid' }
  }

  const state = useProjectStore.getState()
  const { serverConfig, catalogClips, catalogEffects } = state
  if (serverConfig.confirmed && serverConfig.catalogExcludedLicenses.length > 0) {
    try {
      const payload = fromWebProjectJson(data)
      if (
        webProjectUsesExcludedLicense(
          payload.tracks,
          catalogClips,
          catalogEffects,
          serverConfig.catalogExcludedLicenses,
        )
      ) {
        return { ok: false, filename, messageKey: 'file_import_license_unavailable' }
      }
    } catch {
      // fall through to standard validation
    }
  }

  if (serverConfig.confirmed && !serverConfig.glAvailable) {
    const needsGl =
      rawProjectJsonRequiresGl(data) ||
      (() => {
        try {
          const payload = fromWebProjectJson(data)
          return webProjectRequiresGl(payload.tracks, catalogClips, catalogEffects)
        } catch {
          return false
        }
      })()
    if (needsGl) {
      return { ok: false, filename, messageKey: 'file_import_gl_unavailable' }
    }
  }

  try {
    const payload = fromWebProjectJson(data)
    return { ok: true, payload, filename }
  } catch {
    return { ok: false, filename, messageKey: 'file_import_invalid' }
  }
}

export async function parseProjectImportFile(file: File): Promise<ProjectImportParseResult> {
  try {
    const text = await file.text()
    return parseProjectJsonText(text, file.name)
  } catch {
    return { ok: false, filename: file.name, messageKey: 'file_import_invalid' }
  }
}

export function executeProjectImport(
  payload: ProjectImportPayload,
  options?: { importBundleId?: string | null },
): void {
  stopPlaybackOnApiLoss()
  const state = useProjectStore.getState()
  state.setSettingsPanelOpen(false)
  state.loadProject({
    meta: payload.meta,
    typography: payload.typography,
    colors: payload.colors,
    paletteSource: payload.paletteSource,
    tracks: payload.tracks,
    sounds: payload.sounds,
    timelineLayout: payload.timelineLayout,
    projectSettings: [],
    importBundleId: options?.importBundleId ?? null,
  })
}

export type ProjectBundleExportResult =
  | { ok: true }
  | { ok: false; messageKey: TranslationKey; detail?: string }

export async function exportProjectBundle(): Promise<ProjectBundleExportResult> {
  const state = useProjectStore.getState()
  const project = toWebProjectJson({
    meta: state.meta,
    tracks: state.tracks,
    sounds: state.sounds,
    projectSettings: state.projectSettings,
    typography: state.typography,
    colors: state.colors,
    paletteSource: state.paletteSource,
    locale: state.appSettings.locale,
    timelineLayout: state.timelineLayout,
  })

  try {
    const { blob, filename } = await apiExportProjectBundle(project)
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = filename
    anchor.click()
    URL.revokeObjectURL(url)
    return { ok: true }
  } catch (err) {
    if (isBundleExportMissingError(err)) {
      const detail = err.missingFiles.join(', ')
      return { ok: false, messageKey: 'file_bundle_export_missing', detail }
    }
    return {
      ok: false,
      messageKey: 'file_bundle_export_failed',
      detail: err instanceof Error ? err.message : undefined,
    }
  }
}

export type ProjectBundleImportParseResult =
  | { ok: true; payload: ProjectImportPayload; importBundleId: string; filename: string }
  | { ok: false; filename: string; messageKey: TranslationKey; detail?: string }

export async function parseProjectBundleImportFile(
  file: File,
): Promise<ProjectBundleImportParseResult> {
  try {
    const response = await apiImportProjectBundle(file)
    const payload = fromWebProjectJson(response.project)
    return {
      ok: true,
      payload,
      importBundleId: response.import_bundle_id,
      filename: file.name,
    }
  } catch (err) {
    const detail = err instanceof Error ? err.message : undefined
    if (isGlUnavailableApiDetail(detail)) {
      return {
        ok: false,
        filename: file.name,
        messageKey: 'file_import_gl_unavailable',
        detail,
      }
    }
    return {
      ok: false,
      filename: file.name,
      messageKey: 'file_bundle_import_failed',
      detail,
    }
  }
}

export function exportProjectJson(): void {
  const state = useProjectStore.getState()
  const json = toRenderJob({
    meta: state.meta,
    tracks: state.tracks,
    sounds: state.sounds,
    projectSettings: state.projectSettings,
    typography: state.typography,
    colors: state.colors,
    paletteSource: state.paletteSource,
    locale: state.appSettings.locale,
    catalogDetailCache: state.catalogDetailCache,
  })
  const blob = new Blob([JSON.stringify(json, null, 2) + '\n'], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = exportFilenameFromTitle(state.meta.title)
  anchor.click()
  URL.revokeObjectURL(url)
}
