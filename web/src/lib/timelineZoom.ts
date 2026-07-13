/** Matches `@xzdarcy/react-timeline-editor` defaults (Gi, Wi, Go). */
export const TIMELINE_START_LEFT = 20
export const TIMELINE_SCALE_WIDTH = 160
/** Extra ruler columns past project end (`Go` in the timeline lib). */
export const TIMELINE_SCALE_PADDING = 5

export const ZOOM_STEPS = [1, 2, 5, 10, 15, 20, 30, 45, 60, 90, 120, 180, 300, 600] as const

export function timelineMinScaleCount(duration: number, scale: number): number {
  if (scale <= 0) return TIMELINE_SCALE_PADDING + 1
  return Math.ceil(duration / scale) + TIMELINE_SCALE_PADDING
}

export function timelineScrollWidth(duration: number, scale: number): number {
  return timelineMinScaleCount(duration, scale) * TIMELINE_SCALE_WIDTH
}

/** Largest scale (most zoomed-out) that still fits `viewportWidth`. */
export function computeFitZoomScale(duration: number, viewportWidth: number): number {
  if (duration <= 0) return 10
  const usable = viewportWidth - TIMELINE_START_LEFT - 16
  if (usable <= TIMELINE_SCALE_WIDTH) return Math.max(1, duration)

  const fits = (scale: number) => timelineScrollWidth(duration, scale) <= viewportWidth

  let lo = 1
  let hi = Math.max(duration * 2, 60)
  while (!fits(hi) && hi < 7200) hi *= 2

  while (hi - lo > 0.05) {
    const mid = (lo + hi) / 2
    if (fits(mid)) lo = mid
    else hi = mid
  }
  return Math.max(1, Math.round(lo * 100) / 100)
}

export function maxZoomOutScale(duration: number): number {
  return Math.max(600, Math.ceil(duration * 2))
}

export function nextZoomIn(scale: number): number {
  const prev = [...ZOOM_STEPS].reverse().find((s) => s < scale - 0.001)
  return prev ?? 1
}

export function nextZoomOut(scale: number, duration: number): number {
  const cap = maxZoomOutScale(duration)
  const next = ZOOM_STEPS.find((s) => s > scale + 0.001)
  if (next != null) return Math.min(next, cap)
  return Math.min(cap, Math.round(scale * 1.5 * 10) / 10)
}

export function formatZoomScaleLabel(scale: number): string {
  if (scale >= 100) return `${Math.round(scale)}s`
  if (Math.abs(scale - Math.round(scale)) < 0.05) return `${Math.round(scale)}s`
  return `${scale.toFixed(1)}s`
}
