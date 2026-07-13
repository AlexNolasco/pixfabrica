import {
  TIMELINE_SCALE_WIDTH,
  TIMELINE_START_LEFT,
} from '@/lib/timelineZoom'

const CLIP_OR_HANDLE_SELECTOR =
  '.timeline-editor-action, .timeline-editor-cursor, .timeline-editor-cursor-area'

/** True when the event target is a clip, resize handle, or playhead — not empty lane/ruler. */
export function isTimelineClipTarget(target: EventTarget | null): boolean {
  if (!(target instanceof Element)) return false
  return !!target.closest(CLIP_OR_HANDLE_SELECTOR)
}

/** Map a viewport X coordinate to timeline seconds (clamped to `[0, maxDuration]`). */
export function timelineClientXToTime(
  clientX: number,
  areaRect: DOMRect,
  scrollLeft: number,
  scale: number,
  maxDuration: number,
): number {
  const position = clientX - areaRect.left
  const left = Math.max(position + scrollLeft, TIMELINE_START_LEFT)
  const time = ((left - TIMELINE_START_LEFT) / TIMELINE_SCALE_WIDTH) * scale
  return Math.max(0, Math.min(maxDuration, time))
}
