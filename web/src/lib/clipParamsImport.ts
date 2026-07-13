import type { ExportedClipParams } from '@/lib/clipParamsExport'
import type { ControlSpec, ClipCatalogDetail } from '@/lib/catalogDetail'
import { TIMING_SECTION_ID } from '@/lib/catalogDetail'
import { coerceParamValue } from '@/lib/paramValidation'

/** Wire format id for clipboard clip params. */
export const CLIP_PARAMS_FORMAT = 'pixfabrica/clip-params' as const
export const CLIP_PARAMS_FORMAT_VERSION = 1

/** Never imported — timeline / identity live on the clip, not pasted params. */
export const IMPORT_STRUCTURAL_PARAM_KEYS = new Set([
  'id',
  'start',
  'duration',
  'enabled',
])

export type ImportClipParamsErrorCode =
  | 'invalid_json'
  | 'invalid_format'
  | 'unsupported_format_version'
  | 'missing_params'
  | 'plugin_id_mismatch'
  | 'clip_type_mismatch'

export type ImportClipParamsError = {
  code: ImportClipParamsErrorCode
  detail?: string
}

export type ImportClipParamsReport = {
  params: Record<string, unknown>
  defaultedFields: string[]
  unknownFields: string[]
  structuralSkipped: string[]
}

function schemaProp(
  parametersSchema: Record<string, unknown>,
  field: string,
): Record<string, unknown> | null {
  const props = parametersSchema.properties
  if (!props || typeof props !== 'object') return null
  const p = (props as Record<string, unknown>)[field]
  return p && typeof p === 'object' ? (p as Record<string, unknown>) : null
}

function defaultForField(defaults: Record<string, unknown>, field: string): unknown {
  return Object.prototype.hasOwnProperty.call(defaults, field) ? defaults[field] : undefined
}

function numberBounds(
  control: ControlSpec,
  prop: Record<string, unknown> | null,
): { min?: number; max?: number; step?: number } {
  const min =
    typeof control.minimum === 'number'
      ? control.minimum
      : typeof prop?.minimum === 'number'
        ? (prop.minimum as number)
        : undefined
  const max =
    typeof control.maximum === 'number'
      ? control.maximum
      : typeof prop?.maximum === 'number'
        ? (prop.maximum as number)
        : undefined
  const step =
    typeof control.step === 'number'
      ? control.step
      : typeof prop?.multipleOf === 'number'
        ? (prop.multipleOf as number)
        : undefined
  return { min, max, step }
}

function isOnStep(value: number, min: number | undefined, step: number): boolean {
  const base = min ?? 0
  const units = (value - base) / step
  return Math.abs(units - Math.round(units)) < 1e-9
}

function isValidImportNumber(
  raw: unknown,
  control: ControlSpec,
  prop: Record<string, unknown> | null,
  enforceStep = true,
): boolean {
  if (typeof raw !== 'number' || !Number.isFinite(raw)) return false
  const { min, max, step } = numberBounds(control, prop)
  if (min !== undefined && raw < min) return false
  if (max !== undefined && raw > max) return false
  if (enforceStep && step !== undefined && step > 0 && !isOnStep(raw, min, step)) return false
  return true
}

function isValidColorStopList(raw: unknown, control: ControlSpec): boolean {
  if (!Array.isArray(raw)) return false
  const minItems = typeof control.min_items === 'number' ? control.min_items : 0
  const maxItems = typeof control.max_items === 'number' ? control.max_items : undefined
  if (raw.length < minItems) return false
  if (maxItems !== undefined && raw.length > maxItems) return false
  return raw.every((item) => item !== null && typeof item === 'object' && !Array.isArray(item))
}

export function isValidImportValue(
  field: string,
  raw: unknown,
  control: ControlSpec,
  parametersSchema: Record<string, unknown>,
  options?: { enforceStep?: boolean },
): boolean {
  const enforceStep = options?.enforceStep !== false
  const kind = control.kind
  const prop = schemaProp(parametersSchema, field)

  if (kind === 'toggle') {
    return typeof raw === 'boolean'
  }

  if (kind === 'select' || kind === 'segmented_enum') {
    const opts = control.options
    if (!Array.isArray(opts)) return false
    return typeof raw === 'string' && opts.map(String).includes(raw)
  }

  if (kind === 'bus_select') {
    if (raw === null || raw === undefined || raw === '') return true
    return typeof raw === 'string'
  }

  if (kind === 'theme_or_color' || kind === 'text' || kind === 'textarea' || kind === 'file') {
    if (control.nullable && (raw === null || raw === '')) return true
    return typeof raw === 'string'
  }

  if (kind === 'number' || kind === 'slider' || kind === 'camera_orbit') {
    return isValidImportNumber(raw, control, prop, enforceStep)
  }

  if (kind === 'color_stop_list' || kind === 'color_list') {
    return isValidColorStopList(raw, control)
  }

  if (kind === 'hidden') {
    return raw !== undefined
  }

  const defType = typeof prop?.default
  if (defType === 'undefined') {
    return raw !== undefined && raw !== null
  }
  if (defType === 'object') {
    return raw !== null && typeof raw === 'object'
  }
  return typeof raw === defType
}

/** Param fields the properties form exposes (excludes timing / identity). */
export function editableParamFields(detail: ClipCatalogDetail): Set<string> {
  const controls = (detail.ui.controls ?? {}) as Record<string, ControlSpec>
  const sections = Array.isArray(detail.ui.sections) ? detail.ui.sections : []
  const fields = new Set<string>()

  for (const sec of sections) {
    if (!sec || typeof sec !== 'object') continue
    if ((sec as { id?: string }).id === TIMING_SECTION_ID) continue
    const secFields = (sec as { fields?: unknown }).fields
    if (!Array.isArray(secFields)) continue
    for (const field of secFields) {
      if (typeof field !== 'string') continue
      if (IMPORT_STRUCTURAL_PARAM_KEYS.has(field)) continue
      const control = controls[field]
      if (!control || control.kind === 'hidden') continue
      fields.add(field)
    }
  }

  return fields
}

/** Fields whose effective values fail schema/UI validation (for editor warnings). */
export function listInvalidParamFields(
  detail: ClipCatalogDetail,
  params: Record<string, unknown>,
): string[] {
  const controls = (detail.ui.controls ?? {}) as Record<string, ControlSpec>
  const editable = editableParamFields(detail)
  const invalid: string[] = []

  for (const field of editable) {
    const control = controls[field]
    if (!control) continue
    const effective = Object.prototype.hasOwnProperty.call(params, field)
      ? params[field]
      : detail.defaults[field]
    if (effective === undefined || effective === null) continue
    const value =
      (control.kind === 'number' || control.kind === 'slider') &&
      typeof effective === 'number' &&
      Number.isFinite(effective)
        ? coerceParamValue(field, effective, control, detail.parameters_schema)
        : effective
    if (
      !isValidImportValue(field, value, control, detail.parameters_schema, {
        enforceStep: false,
      })
    ) {
      invalid.push(field)
    }
  }

  return invalid.sort()
}

function coerceImportField(
  field: string,
  raw: unknown,
  control: ControlSpec,
  detail: ClipCatalogDetail,
): unknown {
  if (isValidImportValue(field, raw, control, detail.parameters_schema)) {
    return raw
  }
  return defaultForField(detail.defaults, field)
}

export function parseClipParamsClipboard(
  text: string,
): { ok: true; payload: ExportedClipParams } | { ok: false; error: ImportClipParamsError } {
  let parsed: unknown
  try {
    parsed = JSON.parse(text)
  } catch {
    return { ok: false, error: { code: 'invalid_json' } }
  }

  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    return { ok: false, error: { code: 'invalid_format' } }
  }

  const record = parsed as Record<string, unknown>
  if (record.format !== CLIP_PARAMS_FORMAT) {
    return { ok: false, error: { code: 'invalid_format' } }
  }
  if (record.format_version !== CLIP_PARAMS_FORMAT_VERSION) {
    return {
      ok: false,
      error: {
        code: 'unsupported_format_version',
        detail: String(record.format_version),
      },
    }
  }
  if (typeof record.plugin_id !== 'string' || !record.plugin_id) {
    return { ok: false, error: { code: 'invalid_format' } }
  }
  if (typeof record.clip_type !== 'string') {
    return { ok: false, error: { code: 'invalid_format' } }
  }
  if (!record.params || typeof record.params !== 'object' || Array.isArray(record.params)) {
    return { ok: false, error: { code: 'missing_params' } }
  }

  const clipType = record.clip_type

  return {
    ok: true,
    payload: {
      format: CLIP_PARAMS_FORMAT,
      format_version: CLIP_PARAMS_FORMAT_VERSION,
      plugin_id: record.plugin_id,
      clip_type: clipType,
      clip_label: typeof record.clip_label === 'string' ? record.clip_label : clipType,
      params: record.params as Record<string, unknown>,
    },
  }
}

export function validateClipParamsIdentity(
  payload: ExportedClipParams,
  expected: { pluginId: string; clipType: string },
): ImportClipParamsError | null {
  const expectedClipType = expected.clipType
  if (payload.plugin_id !== expected.pluginId) {
    return {
      code: 'plugin_id_mismatch',
      detail: payload.plugin_id,
    }
  }
  if (payload.clip_type !== expectedClipType) {
    return {
      code: 'clip_type_mismatch',
      detail: payload.clip_type,
    }
  }
  return null
}

export function mergeImportedClipParams(
  detail: ClipCatalogDetail,
  pastedParams: Record<string, unknown>,
): ImportClipParamsReport {
  const controls = (detail.ui.controls ?? {}) as Record<string, ControlSpec>
  const controlKeys = new Set(Object.keys(controls))

  const unknownFields: string[] = []
  const structuralSkipped: string[] = []
  const importedByField = new Map<string, unknown>()

  for (const [key, raw] of Object.entries(pastedParams)) {
    if (IMPORT_STRUCTURAL_PARAM_KEYS.has(key)) {
      structuralSkipped.push(key)
      continue
    }
    if (!controlKeys.has(key)) {
      unknownFields.push(key)
      continue
    }
    importedByField.set(key, raw)
  }

  const defaultedFields: string[] = []
  const merged: Record<string, unknown> = { ...detail.defaults }

  for (const [field, control] of Object.entries(controls)) {
    if (IMPORT_STRUCTURAL_PARAM_KEYS.has(field)) continue
    if (!importedByField.has(field)) continue
    const raw = importedByField.get(field)
    const coerced = coerceImportField(field, raw, control, detail)
    if (!isValidImportValue(field, raw, control, detail.parameters_schema)) {
      defaultedFields.push(field)
    }
    merged[field] = coerced
  }

  return {
    params: merged,
    defaultedFields: defaultedFields.sort(),
    unknownFields: unknownFields.sort(),
    structuralSkipped: structuralSkipped.sort(),
  }
}
