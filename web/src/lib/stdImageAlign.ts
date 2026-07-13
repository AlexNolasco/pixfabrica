/** Bounds anchor fractions snapped when image-style align presets change. */

export const STD_IMAGE_CLIP_TYPE = 'std-image'
export const STD_TIME_COUNTER_CLIP_TYPE = 'std-time-counter'

export const STD_IMAGE_ALIGN_OPTIONS = [
  'topLeading',
  'top',
  'topTrailing',
  'leading',
  'center',
  'trailing',
  'bottomLeading',
  'bottom',
  'bottomTrailing',
] as const

export type StdImageAlign = (typeof STD_IMAGE_ALIGN_OPTIONS)[number]

const ALIGN_PRESET_OFFSETS: Record<StdImageAlign, { offset_x: number; offset_y: number }> = {
  topLeading: { offset_x: 0, offset_y: 0 },
  top: { offset_x: 0.5, offset_y: 0 },
  topTrailing: { offset_x: 1, offset_y: 0 },
  leading: { offset_x: 0, offset_y: 0.5 },
  center: { offset_x: 0.5, offset_y: 0.5 },
  trailing: { offset_x: 1, offset_y: 0.5 },
  bottomLeading: { offset_x: 0, offset_y: 1 },
  bottom: { offset_x: 0.5, offset_y: 1 },
  bottomTrailing: { offset_x: 1, offset_y: 1 },
}

export function isStdImageAlign(value: string): value is StdImageAlign {
  return (STD_IMAGE_ALIGN_OPTIONS as readonly string[]).includes(value)
}

export function stdImageAlignPresetOffsets(
  align: string,
): { offset_x: number; offset_y: number } | null {
  if (!isStdImageAlign(align)) return null
  return ALIGN_PRESET_OFFSETS[align]
}

/** True when the clip uses the full 9-point image align option set. */
export function controlUsesImageAlignPresets(control: {
  kind?: string
  options?: unknown
}): boolean {
  if (control.kind !== 'select' || !Array.isArray(control.options)) return false
  const opts = new Set(control.options as string[])
  return STD_IMAGE_ALIGN_OPTIONS.every((option) => opts.has(option))
}
