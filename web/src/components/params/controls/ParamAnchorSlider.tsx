import { useCallback, useEffect, useRef, useState } from 'react'
import { Slider } from '@/components/ui/slider'
import { useT } from '@/lib/i18n'

function presetActive(value: number, preset: number, step: number): boolean {
  return Math.abs(value - preset) <= step / 2 + 1e-9
}

function decimalPlacesForStep(step: number): number {
  if (step >= 1) return 0
  const s = step.toString()
  if (s.includes('e-')) return Number.parseInt(s.split('e-')[1] ?? '0', 10)
  const dot = s.indexOf('.')
  return dot < 0 ? 0 : s.length - dot - 1
}

function snapToStep(value: number, step: number, min = 0, max = 1): number {
  const snapped = Math.round(value / step) * step
  const places = decimalPlacesForStep(step)
  return Math.min(max, Math.max(min, Number(snapped.toFixed(places))))
}

export function ParamAnchorSlider({
  value,
  axis,
  step,
  onCommit,
}: {
  value: number
  axis: 'x' | 'y'
  step: number
  onCommit: (v: number) => void
}) {
  const t = useT()
  const isX = axis === 'x'

  const draftRef = useRef(value)
  const [draft, setDraft] = useState(value)
  const draggingRef = useRef(false)
  const lastCommittedRef = useRef(value)

  const setDraftValue = useCallback((v: number) => {
    draftRef.current = v
    setDraft(v)
  }, [])

  useEffect(() => {
    const snapped = snapToStep(value, step)
    lastCommittedRef.current = snapped
    if (!draggingRef.current) {
      setDraftValue(snapped)
    }
  }, [value, setDraftValue, step])

  const commitDraft = useCallback(() => {
    const snapped = snapToStep(draftRef.current, step)
    if (snapped === lastCommittedRef.current) return
    lastCommittedRef.current = snapped
    setDraftValue(snapped)
    onCommit(snapped)
  }, [onCommit, setDraftValue, step])

  useEffect(() => {
    const onPointerUp = () => {
      if (!draggingRef.current) return
      draggingRef.current = false
      commitDraft()
    }
    window.addEventListener('pointerup', onPointerUp)
    return () => window.removeEventListener('pointerup', onPointerUp)
  }, [commitDraft])

  const presets = isX
    ? ([
        { value: 0, label: t('param_anchor_left') },
        { value: 0.5, label: t('param_anchor_center') },
        { value: 1, label: t('param_anchor_right') },
      ] as const)
    : ([
        { value: 0, label: t('param_anchor_top') },
        { value: 0.5, label: t('param_anchor_center') },
        { value: 1, label: t('param_anchor_bottom') },
      ] as const)

  const markerX = isX ? draft : 0.5
  const markerY = isX ? 0.5 : draft

  const formatValue = (v: number) => {
    if (presetActive(v, 0, step)) return isX ? t('param_anchor_left') : t('param_anchor_top')
    if (presetActive(v, 0.5, step)) return t('param_anchor_center')
    if (presetActive(v, 1, step)) return isX ? t('param_anchor_right') : t('param_anchor_bottom')
    return v.toFixed(decimalPlacesForStep(step))
  }

  const commitPreset = (v: number) => {
    draggingRef.current = false
    setDraftValue(v)
    if (v !== lastCommittedRef.current) {
      lastCommittedRef.current = v
      onCommit(v)
    }
  }

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center gap-2">
        <div
          className="relative h-8 w-10 shrink-0 overflow-hidden rounded border border-border bg-muted/25"
          aria-hidden
        >
          <div
            className={`absolute bg-border/60 ${isX ? 'top-0 bottom-0 w-px' : 'left-0 right-0 h-px'}`}
            style={
              isX
                ? { left: '50%', transform: 'translateX(-50%)' }
                : { top: '50%', transform: 'translateY(-50%)' }
            }
          />
          <div
            className="absolute size-2 -translate-x-1/2 -translate-y-1/2 rounded-full border border-primary bg-background ring-1 ring-primary/40"
            style={{
              left: `${markerX * 100}%`,
              top: `${markerY * 100}%`,
            }}
          />
        </div>

        <div className="flex min-w-0 flex-1 flex-wrap gap-0.5">
          {presets.map((preset) => (
            <button
              key={preset.value}
              type="button"
              className={`rounded px-1.5 py-0.5 text-[10px] ${
                presetActive(draft, preset.value, step)
                  ? 'bg-primary/20 text-primary ring-1 ring-primary/40'
                  : 'bg-muted/60 text-muted-foreground hover:bg-muted'
              }`}
              onClick={() => commitPreset(preset.value)}
            >
              {preset.label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex items-center gap-2">
        <Slider
          className="min-w-0 flex-1"
          min={0}
          max={1}
          step={step}
          value={[draft]}
          onPointerDown={() => {
            draggingRef.current = true
          }}
          onValueChange={(vals) => {
            const d = Array.isArray(vals) ? (vals[0] ?? 0) : Number(vals)
            draggingRef.current = true
            setDraftValue(snapToStep(d, step))
          }}
          onBlur={commitDraft}
        />
        <span className="w-11 shrink-0 truncate text-right font-mono text-[10px] text-foreground tabular-nums">
          {formatValue(draft)}
        </span>
      </div>
    </div>
  )
}
