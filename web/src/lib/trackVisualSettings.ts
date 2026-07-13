import type { Track, Transition } from '@/store/projectStore'

export const LAYOUT_OPTIONS = ['fill', 'vertical', 'horizontal'] as const
export type LayoutOption = (typeof LAYOUT_OPTIONS)[number]

export const DEFAULT_HEADER_FRACTION = 0.2
export const HEADER_FRACTION_MIN = 0.1
export const HEADER_FRACTION_MAX = 0.5
/** Slider snap points as fractions; 0.5 means equal split (stored as null). */
export const HEADER_FRACTION_SNAPS = [0.2, 0.3, 0.4, 0.5] as const

export function isSplitLayout(layout: LayoutOption): boolean {
  return layout === 'vertical' || layout === 'horizontal'
}

/** Auto-weight when a vertical/horizontal track reaches two clips. */
export function bandLayoutPatchForSecondClip(track: {
  layout: LayoutOption
  headerFraction?: number | null
}): { headerFraction: number } | null {
  if (!isSplitLayout(track.layout)) return null
  if (track.headerFraction != null) return null
  return { headerFraction: DEFAULT_HEADER_FRACTION }
}

/** Auto-weight when switching to a split layout with two clips already present. */
export function bandLayoutPatchForLayoutChange(
  layout: LayoutOption,
  clipCount: number,
  headerFraction: number | null | undefined,
): { headerFraction: number } | null {
  if (clipCount !== 2 || !isSplitLayout(layout)) return null
  if (headerFraction != null) return null
  return { headerFraction: DEFAULT_HEADER_FRACTION }
}

export function parseHeaderFraction(raw: unknown): number | null {
  if (typeof raw !== 'number' || !Number.isFinite(raw)) return null
  if (raw < HEADER_FRACTION_MIN || raw > HEADER_FRACTION_MAX) return null
  return raw
}

/** Slider percent (10–50); 50 means equal split (null). */
export function headerFractionToSliderPercent(headerFraction: number | null | undefined): number {
  if (headerFraction == null) return HEADER_FRACTION_MAX * 100
  return Math.round(headerFraction * 100)
}

export function sliderPercentToHeaderFraction(percent: number): number | null {
  const clamped = Math.min(HEADER_FRACTION_MAX * 100, Math.max(HEADER_FRACTION_MIN * 100, percent))
  if (clamped >= HEADER_FRACTION_MAX * 100) return null
  return clamped / 100
}

export const TRANSITION_TYPES = ['fade', 'slide', 'scale', 'blur', 'wipe'] as const
export type TransitionTypeOption = (typeof TRANSITION_TYPES)[number]

export const EASING_OPTIONS = ['linear', 'ease_in', 'ease_out', 'ease_in_out'] as const
export type EasingOption = (typeof EASING_OPTIONS)[number]

export const DIRECTION_OPTIONS = ['left', 'right', 'up', 'down'] as const
export type DirectionOption = (typeof DIRECTION_OPTIONS)[number]

export const DEFAULT_TRANSITION_DURATION = 0.5
export const DEFAULT_TRANSITION_EASING: EasingOption = 'ease_in_out'
export const DEFAULT_TRANSITION_DIRECTION: DirectionOption = 'left'

export function defaultTransition(type: TransitionTypeOption): Transition {
  return {
    type,
    duration: DEFAULT_TRANSITION_DURATION,
    easing: DEFAULT_TRANSITION_EASING,
    direction: DEFAULT_TRANSITION_DIRECTION,
  }
}

export function trackShowsLayout(trackType: Track['trackType'] | undefined): boolean {
  const type = trackType ?? 'skia'
  return type === 'skia' || type === 'gl'
}

export function trackShowsEffects(trackType: Track['trackType'] | undefined): boolean {
  return trackShowsLayout(trackType)
}

export function trackShowsTransitions(trackType: Track['trackType'] | undefined): boolean {
  const type = trackType ?? 'skia'
  return type === 'skia' || type === 'gl' || type === 'post'
}

export function transitionUsesDirection(type: TransitionTypeOption): boolean {
  return type === 'slide' || type === 'wipe'
}

export function resolvedTrackDuration(track: Track, projectDuration: number): number {
  return track.duration ?? projectDuration
}

export function mergeTransitionType(
  existing: Transition | undefined,
  type: TransitionTypeOption,
): Transition {
  if (!existing) return defaultTransition(type)
  return {
    ...existing,
    type,
    direction: existing.direction ?? DEFAULT_TRANSITION_DIRECTION,
  }
}

export function applyTransitionGridChoice(
  current: Transition | undefined,
  id: 'none' | TransitionTypeOption,
): Transition | undefined {
  if (id === 'none') return undefined
  if (!current) return defaultTransition(id)
  return mergeTransitionType(current, id)
}
