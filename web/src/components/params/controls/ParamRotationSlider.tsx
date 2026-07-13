import { useCallback, useEffect, useRef, useState } from 'react'
import { Slider } from '@/components/ui/slider'

function decimalPlacesForStep(step: number): number {
  if (step >= 1) return 0
  const s = step.toString()
  if (s.includes('e-')) return Number.parseInt(s.split('e-')[1] ?? '0', 10)
  const dot = s.indexOf('.')
  return dot < 0 ? 0 : s.length - dot - 1
}

function snapToStep(value: number, step: number, min: number, max: number): number {
  const snapped = min + Math.round((value - min) / step) * step
  const places = decimalPlacesForStep(step)
  return Math.min(max, Math.max(min, Number(snapped.toFixed(places))))
}

function presetActive(value: number, preset: number, step: number): boolean {
  return Math.abs(value - preset) <= step / 2 + 1e-9
}

function toDisplayIndex(value: number, minimum: number, step: number): number {
  return (value - minimum) / step
}

function fromDisplayIndex(index: number, minimum: number, step: number): number {
  return minimum + index * step
}

export function ParamRotationSlider({
  value,
  minimum,
  maximum,
  step,
  presets,
  onCommit,
}: {
  value: number
  minimum: number
  maximum: number
  step: number
  presets?: number[]
  onCommit: (v: number) => void
}) {
  const presetList = presets ?? []
  const displayMax = (maximum - minimum) / step

  const draftRef = useRef(value)
  const [draft, setDraft] = useState(value)
  const draggingRef = useRef(false)
  const lastCommittedRef = useRef(value)

  const setDraftValue = useCallback((v: number) => {
    draftRef.current = v
    setDraft(v)
  }, [])

  useEffect(() => {
    const snapped = snapToStep(value, step, minimum, maximum)
    lastCommittedRef.current = snapped
    if (!draggingRef.current) {
      setDraftValue(snapped)
    }
  }, [value, setDraftValue, step, minimum, maximum])

  const commitDraft = useCallback(() => {
    const snapped = snapToStep(draftRef.current, step, minimum, maximum)
    if (snapped === lastCommittedRef.current) return
    lastCommittedRef.current = snapped
    setDraftValue(snapped)
    onCommit(snapped)
  }, [onCommit, setDraftValue, step, minimum, maximum])

  useEffect(() => {
    const onPointerUp = () => {
      if (!draggingRef.current) return
      draggingRef.current = false
      commitDraft()
    }
    window.addEventListener('pointerup', onPointerUp)
    return () => window.removeEventListener('pointerup', onPointerUp)
  }, [commitDraft])

  const commitPreset = (v: number) => {
    const snapped = snapToStep(v, step, minimum, maximum)
    draggingRef.current = false
    setDraftValue(snapped)
    if (snapped !== lastCommittedRef.current) {
      lastCommittedRef.current = snapped
      onCommit(snapped)
    }
  }

  const formatDegrees = (v: number) => {
    const places = decimalPlacesForStep(step)
    const rounded = places === 0 ? Math.round(v) : Number(v.toFixed(places))
    return `${rounded}°`
  }

  const displayValue = toDisplayIndex(draft, minimum, step)

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center gap-2">
        <div
          className="relative h-8 w-10 shrink-0 overflow-hidden rounded border border-border bg-muted/25"
          aria-hidden
        >
          <div
            className="absolute left-1/2 top-1/2 h-3.5 w-5 rounded-sm border border-primary/70 bg-primary/15"
            style={{ transform: `translate(-50%, -50%) rotate(${draft}deg)` }}
          />
        </div>

        {presetList.length > 0 ? (
          <div className="flex min-w-0 flex-1 flex-wrap gap-0.5">
            {presetList.map((preset) => (
              <button
                key={preset}
                type="button"
                className={`rounded px-1.5 py-0.5 text-[10px] tabular-nums ${
                  presetActive(draft, preset, step)
                    ? 'bg-primary/20 text-primary ring-1 ring-primary/40'
                    : 'bg-muted/60 text-muted-foreground hover:bg-muted'
                }`}
                onClick={() => commitPreset(preset)}
              >
                {formatDegrees(preset)}
              </button>
            ))}
          </div>
        ) : null}
      </div>

      <div className="flex items-center gap-2">
        <Slider
          className="min-w-0 flex-1"
          min={0}
          max={displayMax}
          step={1}
          value={[displayValue]}
          onPointerDown={() => {
            draggingRef.current = true
          }}
          onValueChange={(vals) => {
            const index = Array.isArray(vals) ? (vals[0] ?? 0) : Number(vals)
            draggingRef.current = true
            setDraftValue(
              snapToStep(fromDisplayIndex(index, minimum, step), step, minimum, maximum),
            )
          }}
          onBlur={commitDraft}
        />
        <span className="w-11 shrink-0 truncate text-right font-mono text-[10px] text-foreground tabular-nums">
          {formatDegrees(draft)}
        </span>
      </div>
    </div>
  )
}
