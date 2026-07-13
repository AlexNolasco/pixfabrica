import { useCallback, useEffect, type RefObject } from 'react'
import { useT } from '@/lib/i18n'
import { samplePreviewCanvasColor } from '@/lib/samplePreviewCanvasColor'
import { useColorPickStore } from '@/store/colorPickStore'
import { useToastStore } from '@/store/toastStore'

export function usePreviewCanvasColorPick(
  canvasRef: RefObject<HTMLCanvasElement | null>,
  hasFrame: boolean,
) {
  const t = useT()
  const active = useColorPickStore((s) => s.active)
  const cancelPick = useColorPickStore((s) => s.cancelPick)
  const completePick = useColorPickStore((s) => s.completePick)
  const pushToast = useToastStore((s) => s.pushToast)

  useEffect(() => {
    if (!active) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') cancelPick()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [active, cancelPick])

  const onCanvasPointerDown = useCallback(
    (event: React.PointerEvent<HTMLCanvasElement>) => {
      if (!active) return
      event.preventDefault()
      event.stopPropagation()

      if (!hasFrame) {
        pushToast(t('color_pick_no_preview'), 'warn')
        return
      }

      const canvas = canvasRef.current
      if (!canvas) return

      const hex = samplePreviewCanvasColor(canvas, event.clientX, event.clientY)
      if (!hex) {
        pushToast(t('color_pick_transparent'), 'warn')
        return
      }
      completePick(hex)
    },
    [active, hasFrame, canvasRef, completePick, pushToast, t],
  )

  return { pickActive: active, onCanvasPointerDown }
}
