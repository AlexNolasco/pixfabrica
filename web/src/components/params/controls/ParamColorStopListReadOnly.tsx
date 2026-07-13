import { resolveSwatch } from '@/lib/themeColor'

type StopRow = { color?: unknown; position?: unknown }

export function ParamColorStopListReadOnly({
  value,
  itemLabel,
  jobTheme,
}: {
  value: unknown
  itemLabel: string
  jobTheme?: Record<string, string>
}) {
  const rows = Array.isArray(value) ? (value as StopRow[]) : []
  if (rows.length === 0) {
    return <p className="text-[10px] text-muted-foreground italic">No stops</p>
  }
  return (
    <ul className="flex flex-col gap-1">
      {rows.map((row, i) => (
        <li
          key={i}
          className="flex items-center gap-2 rounded border border-border/60 bg-muted/30 px-2 py-1"
        >
          <span
            className="h-5 w-5 shrink-0 rounded border border-border"
            style={{
              backgroundColor: resolveSwatch(row.color, jobTheme),
            }}
          />
          <span className="flex-1 text-[10px] text-muted-foreground">{itemLabel}</span>
          <span className="font-mono text-[10px] text-foreground">
            {row.position != null ? String(row.position) : '—'}
          </span>
        </li>
      ))}
    </ul>
  )
}
