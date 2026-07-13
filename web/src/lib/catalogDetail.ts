export interface ClipCatalogLabels {
  sections: Record<string, string>
  fields: Record<
    string,
    {
      label: string
      description?: string
      options?: Record<string, string>
      item?: string
    }
  >
  presets?: Record<string, string>
}

export interface ClipCatalogDetail {
  clip_type: string
  plugin_id: string
  ui: Record<string, unknown>
  defaults: Record<string, unknown>
  parameters_schema: Record<string, unknown>
  labels: ClipCatalogLabels
}

export function catalogDetailCacheKey(clipType: string, locale: string): string {
  return `${clipType}:${locale}`
}

export function catalogEffectType(item: { effect_type: string }): string {
  return item.effect_type
}

export function normalizeCatalogEffect<T extends { effect_type: string }>(
  raw: T,
): T & { effect_type: string } {
  return {
    ...raw,
    effect_type: raw.effect_type,
  }
}

export function paramsNeedDefaultsHydration(params: Record<string, unknown>): boolean {
  return Object.keys(params).length === 0
}

export const TIMING_SECTION_ID = 'timing'

export type ControlKind =
  | 'hidden'
  | 'text'
  | 'textarea'
  | 'number'
  | 'slider'
  | 'file'
  | 'toggle'
  | 'select'
  | 'typography_role'
  | 'segmented_enum'
  | 'theme_or_color'
  | 'bus_select'
  | 'color_stop_list'
  | 'color_list'
  | 'camera_orbit'
  | 'unknown'

export interface ControlSpec {
  kind: ControlKind
  [key: string]: unknown
}

export function isImmediateControlKind(kind: ControlKind): boolean {
  return (
    kind === 'toggle' ||
    kind === 'select' ||
    kind === 'typography_role' ||
    kind === 'segmented_enum' ||
    kind === 'theme_or_color' ||
    kind === 'bus_select'
  )
}
