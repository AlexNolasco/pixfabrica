import { type RefObject, useEffect } from 'react'
import {
  isTimelineClipTarget,
  timelineClientXToTime,
} from '@/lib/timelineScrub'

type ScrubMode = 'ruler' | 'lane'

export function useTimelinePointerScrub({
  containerRef,
  scrollLeftRef,
  scaleRef,
  durationRef,
  playing,
  onScrubStart,
  onScrubPreview,
  onScrubEnd,
}: {
  containerRef: RefObject<HTMLDivElement | null>
  scrollLeftRef: RefObject<number>
  scaleRef: RefObject<number>
  durationRef: RefObject<number>
  playing: boolean
  onScrubStart: () => void
  onScrubPreview: (time: number) => void
  onScrubEnd: (time: number) => void
}) {
  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const timeInteract = () =>
      container.querySelector<HTMLElement>('.timeline-editor-time-area-interact')
    const editArea = () =>
      container.querySelector<HTMLElement>('.timeline-editor-edit-area')

    let mode: ScrubMode | null = null
    let captureEl: HTMLElement | null = null

    const resolveTime = (clientX: number, scrubMode: ScrubMode): number | null => {
      const root = scrubMode === 'ruler' ? timeInteract() : editArea()
      if (!root) return null
      return timelineClientXToTime(
        clientX,
        root.getBoundingClientRect(),
        scrollLeftRef.current,
        scaleRef.current,
        durationRef.current,
      )
    }

    const onPointerDown = (e: PointerEvent) => {
      if (playing) return
      if (e.button !== 0) return
      if (isTimelineClipTarget(e.target)) return

      const target = e.target
      if (!(target instanceof Element)) return

      const ti = timeInteract()
      const ea = editArea()

      if (ti?.contains(target)) {
        mode = 'ruler'
        captureEl = ti
      } else if (ea?.contains(target) && target.closest('.timeline-editor-edit-row')) {
        mode = 'lane'
        captureEl = ea
      } else {
        return
      }

      const t = resolveTime(e.clientX, mode)
      if (t == null) {
        mode = null
        captureEl = null
        return
      }

      e.preventDefault()
      captureEl.setPointerCapture(e.pointerId)
      onScrubStart()
      onScrubPreview(t)
    }

    const onPointerMove = (e: PointerEvent) => {
      if (!mode) return
      const t = resolveTime(e.clientX, mode)
      if (t != null) onScrubPreview(t)
    }

    const finishScrub = (e: PointerEvent) => {
      if (!mode) return
      const scrubMode = mode
      const t = resolveTime(e.clientX, scrubMode)
      try {
        captureEl?.releasePointerCapture(e.pointerId)
      } catch {
        /* pointer already released */
      }
      mode = null
      captureEl = null
      if (t != null) onScrubEnd(t)
    }

    container.addEventListener('pointerdown', onPointerDown)
    container.addEventListener('pointermove', onPointerMove)
    container.addEventListener('pointerup', finishScrub)
    container.addEventListener('pointercancel', finishScrub)
    return () => {
      container.removeEventListener('pointerdown', onPointerDown)
      container.removeEventListener('pointermove', onPointerMove)
      container.removeEventListener('pointerup', finishScrub)
      container.removeEventListener('pointercancel', finishScrub)
    }
  }, [
    containerRef,
    scrollLeftRef,
    scaleRef,
    durationRef,
    playing,
    onScrubStart,
    onScrubPreview,
    onScrubEnd,
  ])
}
