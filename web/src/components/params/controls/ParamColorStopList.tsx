import { useCallback, useEffect, useRef, useState } from 'react'
import { Slider } from '@/components/ui/slider'
import { useT } from '@/lib/i18n'
import { ParamThemeOrColor } from './ParamThemeOrColor'

type StopRow = { color: string; position: number }

function posNum(p: unknown, i: number, n: number): number {
  if (typeof p === 'number') return p
  return n <= 1 ? 0 : i / (n - 1)
}

function colorStr(c: unknown): string {
  return typeof c === 'string' ? c : '#ffffff'
}

function hydrateRows(value: unknown): StopRow[] {
  const raw = Array.isArray(value) ? (value as { color?: unknown; position?: unknown }[]) : []
  return raw.map((r, i) => ({
    color: colorStr(r.color),
    position: posNum(r.position, i, raw.length),
  }))
}

function nextAutoPosition(rows: StopRow[]): number {
  if (rows.length === 0) return 0
  if (rows.length === 1) return 1.0
  const positions = [...rows.map((r) => r.position)].sort((a, b) => a - b)
  let bestGap = 0
  let bestMid = 0.5
  for (let i = 0; i < positions.length - 1; i++) {
    const gap = positions[i + 1] - positions[i]
    if (gap > bestGap) {
      bestGap = gap
      bestMid = (positions[i] + positions[i + 1]) / 2
    }
  }
  return Math.round(bestMid * 20) / 20
}

export function ParamColorStopList({
  value,
  minItems = 0,
  maxItems,
  jobTheme,
  onCommit,
}: {
  value: unknown
  minItems?: number
  maxItems?: number
  jobTheme?: Record<string, string>
  onCommit: (stops: StopRow[]) => void
}) {
  const [rows, setRows] = useState<StopRow[]>(() => hydrateRows(value))
  const t = useT()
  const draggingRef = useRef(false)
  const pendingRef = useRef<StopRow[] | null>(null)

  // Sync from prop only when not dragging a slider
  useEffect(() => {
    if (!draggingRef.current) {
      setRows(hydrateRows(value))
    }
  }, [value])

  const commitRows = useCallback(
    (next: StopRow[]) => {
      onCommit(next)
    },
    [onCommit],
  )

  // Commit buffered position changes on pointer release
  useEffect(() => {
    const onPointerUp = () => {
      if (!draggingRef.current) return
      draggingRef.current = false
      if (pendingRef.current !== null) {
        commitRows(pendingRef.current)
        pendingRef.current = null
      }
    }
    window.addEventListener('pointerup', onPointerUp)
    return () => window.removeEventListener('pointerup', onPointerUp)
  }, [commitRows])

  const updatePosition = (index: number, position: number) => {
    const next = rows.map((r, i) => (i === index ? { ...r, position } : r))
    setRows(next)
    pendingRef.current = next
  }

  const updateColor = (index: number, color: string) => {
    const next = rows.map((r, i) => (i === index ? { ...r, color } : r))
    setRows(next)
    commitRows(next)
  }

  const addStop = () => {
    const next = [...rows, { color: '#ffffff', position: nextAutoPosition(rows) }]
    setRows(next)
    commitRows(next)
  }

  const removeStop = (index: number) => {
    const next = rows.filter((_, i) => i !== index)
    setRows(next)
    commitRows(next)
  }

  const distributeEvenly = () => {
    const n = rows.length
    if (n < 2) return
    const next = rows.map((r, i) => ({ ...r, position: Math.round((i / (n - 1)) * 20) / 20 }))
    setRows(next)
    commitRows(next)
  }

  const canAdd = maxItems === undefined || rows.length < maxItems
  const canRemove = rows.length > minItems

  return (
    <div className="flex flex-col gap-1.5">
      {rows.length === 0 && (
        <p className="text-[10px] italic text-muted-foreground">{t('color_stop_empty')}</p>
      )}
      {rows.map((row, i) => (
        <div
          key={i}
          className="flex items-center gap-2 rounded border border-border/60 bg-muted/30 px-2 py-1"
        >
          <ParamThemeOrColor
            value={row.color}
            nullable={false}
            jobTheme={jobTheme}
            onChange={(v) => updateColor(i, v ?? '#ffffff')}
          />
          <Slider
            className="flex-1"
            min={0}
            max={1}
            step={0.05}
            value={[row.position]}
            onPointerDown={() => {
              draggingRef.current = true
            }}
            onValueChange={(vals) => updatePosition(i, Array.isArray(vals) ? (vals[0] ?? row.position) : Number(vals))}
          />
          <span className="w-8 shrink-0 text-right font-mono text-[10px] tabular-nums text-foreground">
            {row.position.toFixed(2)}
          </span>
          <button
            type="button"
            disabled={!canRemove}
            aria-label="Remove stop"
            className="shrink-0 text-[11px] leading-none text-muted-foreground hover:text-destructive disabled:pointer-events-none disabled:opacity-30"
            onClick={() => removeStop(i)}
          >
            ×
          </button>
        </div>
      ))}
      <div className="mt-0.5 flex flex-col gap-1">
        {canAdd && (
          <button
            type="button"
            className="rounded border border-dashed border-border/60 py-0.5 text-[10px] text-muted-foreground hover:border-primary/40 hover:text-primary"
            onClick={addStop}
          >
            {t('color_stop_add')}
          </button>
        )}
        {rows.length >= 2 && (
          <button
            type="button"
            className="rounded border border-border/60 py-0.5 text-[10px] text-muted-foreground hover:border-primary/40 hover:text-primary"
            onClick={distributeEvenly}
          >
            {t('color_stop_distribute')}
          </button>
        )}
      </div>
    </div>
  )
}
