import type { Clip } from '@/store/projectStore'

/** Clipboard JSON for clip params (see clipParamsImport). */
export interface ExportedClipParams {
  format: 'pixfabrica/clip-params'
  format_version: 1
  /** Plugin package that owns the clip kind (e.g. pixfabrica-std). */
  plugin_id: string
  /** Stable clip type id (e.g. std-gradient). */
  clip_type: string
  /** Localized catalog display name for the clip type. */
  clip_label: string
  params: Record<string, unknown>
}

export function humanizeClipType(clipType: string): string {
  const name = clipType.replace(/^std-/, '')
  return name
    .split(/[-_]/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

export function buildClipParamsExport(input: {
  clip: Clip
  pluginId: string
  clipLabel: string
}): ExportedClipParams {
  return {
    format: 'pixfabrica/clip-params',
    format_version: 1,
    plugin_id: input.pluginId,
    clip_type: input.clip.clip_type,
    clip_label: input.clipLabel,
    params: { ...input.clip.params },
  }
}

export function serializeClipParamsExport(payload: ExportedClipParams): string {
  return JSON.stringify(payload, null, 2)
}
