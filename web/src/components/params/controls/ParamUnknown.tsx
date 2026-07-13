export function ParamUnknown({
  label,
  value,
}: {
  label: string
  value: unknown
}) {
  return (
    <div className="rounded border border-dashed border-yellow-500/40 bg-yellow-500/5 px-2 py-1.5">
      <p className="text-[10px] text-yellow-600 dark:text-yellow-400">
        Unsupported control — {label}
      </p>
      <p className="font-mono text-xs text-foreground truncate">{String(value)}</p>
    </div>
  )
}
