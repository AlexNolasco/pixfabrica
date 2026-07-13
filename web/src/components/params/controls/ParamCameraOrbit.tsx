import { useCallback, useEffect, useRef, useState } from 'react'

export function ParamCameraOrbit({
  azimuth,
  elevation,
  onCommit,
  variant = 'camera',
}: {
  azimuth: number
  elevation: number
  onCommit: (az: number, el: number) => void
  variant?: 'camera' | 'light'
}) {
  const azRef = useRef(azimuth)
  const elRef = useRef(elevation)
  const [draftAz, setDraftAz] = useState(azimuth)
  const [draftEl, setDraftEl] = useState(elevation)
  const draggingRef = useRef(false)
  const lastPosRef = useRef({ x: 0, y: 0 })
  const lastCommittedRef = useRef({ az: azimuth, el: elevation })
  const padRef = useRef<HTMLDivElement>(null)

  const setDraft = useCallback((az: number, el: number) => {
    azRef.current = az
    elRef.current = el
    setDraftAz(az)
    setDraftEl(el)
  }, [])

  useEffect(() => {
    lastCommittedRef.current = { az: azimuth, el: elevation }
    if (!draggingRef.current) {
      setDraft(azimuth, elevation)
    }
  }, [azimuth, elevation, setDraft])

  const commitDraft = useCallback(() => {
    const last = lastCommittedRef.current
    if (azRef.current === last.az && elRef.current === last.el) return
    lastCommittedRef.current = { az: azRef.current, el: elRef.current }
    onCommit(azRef.current, elRef.current)
  }, [onCommit])

  useEffect(() => {
    const onUp = () => {
      if (!draggingRef.current) return
      draggingRef.current = false
      commitDraft()
    }
    window.addEventListener('pointerup', onUp)
    return () => window.removeEventListener('pointerup', onUp)
  }, [commitDraft])

  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId)
    draggingRef.current = true
    lastPosRef.current = { x: e.clientX, y: e.clientY }
  }

  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!draggingRef.current) return
    const pad = padRef.current
    if (!pad) return
    const { width, height } = pad.getBoundingClientRect()
    const dx = e.clientX - lastPosRef.current.x
    const dy = e.clientY - lastPosRef.current.y
    lastPosRef.current = { x: e.clientX, y: e.clientY }
    // full width = 360° azimuth; full height = 178° elevation span
    const newAz = ((azRef.current + dx * (360 / width)) % 360 + 360) % 360
    const newEl = Math.max(-89, Math.min(89, elRef.current - dy * (178 / height)))
    setDraft(Math.round(newAz), Math.round(newEl))
  }

  const displayEl = Math.max(-89, Math.min(89, draftEl))
  const azPct = ((draftAz % 360) / 360) * 100
  const elPct = ((89 - displayEl) / 178) * 100
  const isLight = variant === 'light'

  return (
    <div className="flex flex-col gap-1">
      <div
        ref={padRef}
        className={
          isLight
            ? 'relative h-14 w-full cursor-crosshair select-none overflow-hidden rounded border border-amber-500/30 bg-amber-500/5'
            : 'relative h-14 w-full cursor-crosshair select-none overflow-hidden rounded border border-border bg-muted/25'
        }
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
      >
        {/* Vertical grid lines at F(0°) R(90°) B(180°) L(270°) */}
        {([0, 90, 180, 270] as const).map((az) => (
          <div
            key={az}
            className="absolute top-0 bottom-0 w-px bg-border/40"
            style={{ left: `${(az / 360) * 100}%` }}
          />
        ))}
        {/* Horizontal grid lines at +45° 0° -45° */}
        {([-45, 0, 45] as const).map((el) => (
          <div
            key={el}
            className={`absolute left-0 right-0 h-px ${el === 0 ? 'bg-border/60' : 'bg-border/25'}`}
            style={{ top: `${((89 - el) / 178) * 100}%` }}
          />
        ))}
        {/* Position dot */}
        <div
          className={
            isLight
              ? 'pointer-events-none absolute size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full border border-amber-600 bg-amber-400 ring-1 ring-amber-500/50'
              : 'pointer-events-none absolute size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full border border-primary bg-background ring-1 ring-primary/40'
          }
          style={{ left: `${azPct}%`, top: `${elPct}%` }}
        />
      </div>
      {/* Axis labels + live readout */}
      <div className="relative h-3.5 select-none">
        {(['F', 'R', 'B', 'L'] as const).map((label, i) => (
          <span
            key={label}
            className="absolute -translate-x-1/2 text-[9px] text-muted-foreground/40"
            style={{ left: `${(i / 4) * 100}%` }}
          >
            {label}
          </span>
        ))}
        <span className="absolute right-0 font-mono text-[9px] text-muted-foreground tabular-nums">
          {draftAz}° / {draftEl >= 0 ? '+' : ''}{draftEl}°
        </span>
      </div>
    </div>
  )
}
