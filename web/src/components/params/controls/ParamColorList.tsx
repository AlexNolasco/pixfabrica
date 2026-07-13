import { useCallback, useEffect, useState } from 'react'
import { useT } from '@/lib/i18n'
import { ParamThemeOrColor } from './ParamThemeOrColor'

type SwatchRow = { color: string }

function colorStr(c: unknown): string {
  return typeof c === 'string' ? c : '#ffffff'
}

function hydrateRows(value: unknown): SwatchRow[] {
  const raw = Array.isArray(value) ? (value as { color?: unknown }[]) : []
  return raw.map((r) => ({
    color: colorStr(r.color),
  }))
}

export function ParamColorList({
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
  onCommit: (swatches: SwatchRow[]) => void
}) {
  const [rows, setRows] = useState<SwatchRow[]>(() => hydrateRows(value))
  const t = useT()

  useEffect(() => {
    setRows(hydrateRows(value))
  }, [value])

  const commitRows = useCallback(
    (next: SwatchRow[]) => {
      onCommit(next)
    },
    [onCommit],
  )

  const updateColor = (index: number, color: string) => {
    const next = rows.map((r, i) => (i === index ? { ...r, color } : r))
    setRows(next)
    commitRows(next)
  }

  const addSwatch = () => {
    const next = [...rows, { color: '#ffffff' }]
    setRows(next)
    commitRows(next)
  }

  const removeSwatch = (index: number) => {
    const next = rows.filter((_, i) => i !== index)
    setRows(next)
    commitRows(next)
  }

  const canAdd = maxItems === undefined || rows.length < maxItems
  const canRemove = rows.length > minItems

  return (
    <div className="flex flex-col gap-1.5">
      {rows.length === 0 && (
        <p className="text-[10px] italic text-muted-foreground">{t('color_list_empty')}</p>
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
          <button
            type="button"
            disabled={!canRemove}
            aria-label="Remove color"
            className="ml-auto shrink-0 text-[11px] leading-none text-muted-foreground hover:text-destructive disabled:pointer-events-none disabled:opacity-30"
            onClick={() => removeSwatch(i)}
          >
            ×
          </button>
        </div>
      ))}
      {canAdd && (
        <button
          type="button"
          className="rounded border border-dashed border-border/60 py-0.5 text-[10px] text-muted-foreground hover:border-primary/40 hover:text-primary"
          onClick={addSwatch}
        >
          {t('color_list_add')}
        </button>
      )}
    </div>
  )
}
