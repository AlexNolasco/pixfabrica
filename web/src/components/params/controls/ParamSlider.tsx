import { useCallback, useEffect, useRef, useState } from 'react'
import { Slider } from '@/components/ui/slider'

export function ParamSlider({
  value,
  minimum,
  maximum,
  step,
  showAs,
  onCommit,
}: {
  value: number
  minimum: number
  maximum: number
  step: number
  showAs?: string
  onCommit: (v: number) => void
}) {
  const isPercent = showAs === 'percent'
  const displayMin = isPercent ? minimum * 100 : minimum
  const displayMax = isPercent ? maximum * 100 : maximum
  const displayStep = isPercent ? step * 100 : step

  const fromDisplay = (d: number) => (isPercent ? d / 100 : d)
  const toDisplay = (v: number) => (isPercent ? v * 100 : v)

  const draftRef = useRef(value)
  const [draft, setDraft] = useState(value)
  const draggingRef = useRef(false)
  const lastCommittedRef = useRef(value)

  const setDraftValue = useCallback((v: number) => {
    draftRef.current = v
    setDraft(v)
  }, [])

  useEffect(() => {
    lastCommittedRef.current = value
    if (!draggingRef.current) {
      setDraftValue(value)
    }
  }, [value, setDraftValue])

  const commitDraft = useCallback(() => {
    if (draftRef.current === lastCommittedRef.current) return
    lastCommittedRef.current = draftRef.current
    onCommit(draftRef.current)
  }, [onCommit])

  useEffect(() => {
    const onPointerUp = () => {
      if (!draggingRef.current) return
      draggingRef.current = false
      commitDraft()
    }
    window.addEventListener('pointerup', onPointerUp)
    return () => window.removeEventListener('pointerup', onPointerUp)
  }, [commitDraft])

  const displayVal = toDisplay(draft)
  const decimals = displayStep >= 1 ? 0 : displayStep >= 0.1 ? 1 : 2

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-2">
        <Slider
          className="flex-1"
          min={displayMin}
          max={displayMax}
          step={displayStep}
          value={[displayVal]}
          onPointerDown={() => {
            draggingRef.current = true
          }}
          onValueChange={(vals) => {
            const d = Array.isArray(vals) ? (vals[0] ?? displayMin) : Number(vals)
            draggingRef.current = true
            setDraftValue(fromDisplay(d))
          }}
          onBlur={commitDraft}
        />
        <span className="w-12 text-right font-mono text-[10px] text-foreground tabular-nums">
          {isPercent ? `${Math.round(displayVal)}%` : displayVal.toFixed(decimals)}
        </span>
      </div>
    </div>
  )
}
