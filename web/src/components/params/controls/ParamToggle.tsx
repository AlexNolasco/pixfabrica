export function ParamToggle({
  value,
  onChange,
}: {
  value: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <button
      type="button"
      className={`self-start rounded px-2 py-0.5 text-[11px] ${
        value
          ? 'bg-primary/15 text-primary hover:bg-primary/20'
          : 'bg-muted text-muted-foreground hover:bg-muted/80'
      }`}
      onClick={() => onChange(!value)}
    >
      {value ? 'On' : 'Off'}
    </button>
  )
}
