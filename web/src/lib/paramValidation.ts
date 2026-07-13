import type { ControlSpec } from '@/lib/catalogDetail'

function schemaProp(
  parametersSchema: Record<string, unknown>,
  field: string,
): Record<string, unknown> | null {
  const props = parametersSchema.properties
  if (!props || typeof props !== 'object') return null
  const p = (props as Record<string, unknown>)[field]
  return p && typeof p === 'object' ? (p as Record<string, unknown>) : null
}

export function coerceParamValue(
  field: string,
  raw: unknown,
  control: ControlSpec,
  parametersSchema: Record<string, unknown>,
): unknown {
  const kind = control.kind
  const prop = schemaProp(parametersSchema, field)

  if (kind === 'toggle') {
    return Boolean(raw)
  }

  if (kind === 'select' || kind === 'segmented_enum') {
    const opts = control.options
    if (!Array.isArray(opts)) return raw
    const s = String(raw)
    return opts.map(String).includes(s) ? s : opts[0]
  }

  if (kind === 'bus_select') {
    if (raw === null || raw === '' || raw === undefined) return null
    return String(raw)
  }

  if (kind === 'theme_or_color') {
    if (control.nullable && (raw === null || raw === '')) return null
    return typeof raw === 'string' ? raw : String(raw ?? '')
  }

  if (kind === 'text' || kind === 'textarea' || kind === 'file') {
    if (control.nullable && (raw === null || raw === '')) return null
    return typeof raw === 'string' ? raw : String(raw ?? '')
  }

  if (kind === 'number' || kind === 'slider') {
    let n = typeof raw === 'number' ? raw : Number(raw)
    if (!Number.isFinite(n)) {
      const def = prop?.default
      n = typeof def === 'number' ? def : 0
    }
    const mn =
      typeof control.minimum === 'number'
        ? control.minimum
        : typeof prop?.minimum === 'number'
          ? (prop.minimum as number)
          : undefined
    const mx =
      typeof control.maximum === 'number'
        ? control.maximum
        : typeof prop?.maximum === 'number'
          ? (prop.maximum as number)
          : undefined
    if (mn !== undefined) n = Math.max(mn, n)
    if (mx !== undefined) n = Math.min(mx, n)
    const step =
      typeof control.step === 'number'
        ? control.step
        : typeof prop?.multipleOf === 'number'
          ? (prop.multipleOf as number)
          : undefined
    if (step !== undefined && step > 0) {
      const base = mn ?? 0
      n = Math.round((n - base) / step) * step + base
    }
    if (mn !== undefined) n = Math.max(mn, n)
    if (mx !== undefined) n = Math.min(mx, n)
    return n
  }

  return raw
}
