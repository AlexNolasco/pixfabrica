import type { ControlSpec, ClipCatalogDetail } from '@/lib/catalogDetail'
import type { Clip, EffectInstance } from '@/store/projectStore'

export function catalogDetailUsesBusSelect(detail: ClipCatalogDetail | undefined): boolean {
  if (!detail?.ui) return false
  const controls = (detail.ui.controls ?? {}) as Record<string, ControlSpec>
  return Object.values(controls).some((control) => control.kind === 'bus_select')
}

function effectiveBusName(busSelect: unknown): string {
  if (typeof busSelect === 'string' && busSelect.trim()) return busSelect.trim()
  return 'main'
}

function effectSupportsBus(detail: ClipCatalogDetail | undefined): boolean {
  if (!detail?.ui) return false
  const controls = (detail.ui.controls ?? {}) as Record<string, ControlSpec>
  return controls.bus_select?.kind === 'bus_select'
}

function effectBusActive(
  detail: ClipCatalogDetail | undefined,
  params: Record<string, unknown>,
): boolean {
  if (!detail?.ui || !effectSupportsBus(detail)) return false
  const controls = (detail.ui.controls ?? {}) as Record<string, ControlSpec>
  if ('sensitivity' in controls) {
    return Number(params.sensitivity ?? 0) > 0
  }
  return true
}

function resolveEffectBusSelect(
  fx: EffectInstance,
  clip: Clip,
  fxDetail: ClipCatalogDetail | undefined,
  clipDetail: ClipCatalogDetail | undefined,
): string | null {
  if (effectSupportsBus(fxDetail)) {
    const raw = fx.params.bus_select
    if (typeof raw === 'string' && raw.trim()) return raw.trim()
  }
  if (catalogDetailUsesBusSelect(clipDetail)) {
    const parentBus = clip.params.bus_select
    if (typeof parentBus === 'string' && parentBus.trim()) {
      return parentBus.trim()
    }
    return null
  }
  return null
}

/** Bus names an isolated clip preview should inject (mirrors core ``bus_names_needed_for_clip``). */
export function busNamesNeededForClip(
  clip: Clip,
  clipDetail: ClipCatalogDetail | undefined,
  getEffectDetail: (effectType: string) => ClipCatalogDetail | undefined,
): string[] {
  const needed = new Set<string>()
  if (!clip.enabled) return []

  if (catalogDetailUsesBusSelect(clipDetail)) {
    const raw = String(clip.params.bus_select ?? '').trim()
    if (raw) needed.add(effectiveBusName(raw))
  }

  for (const fx of clip.effects ?? []) {
    if (fx.enabled === false) continue
    const fxDetail = getEffectDetail(fx.effect_type)
    if (!effectBusActive(fxDetail, fx.params)) continue
    needed.add(
      effectiveBusName(resolveEffectBusSelect(fx, clip, fxDetail, clipDetail)),
    )
  }

  return [...needed]
}

export function clipNeedsBusPreview(
  clip: Clip | undefined,
  clipDetail: ClipCatalogDetail | undefined,
  getEffectDetail: (effectType: string) => ClipCatalogDetail | undefined,
): boolean {
  if (!clip) return false
  return busNamesNeededForClip(clip, clipDetail, getEffectDetail).length > 0
}
