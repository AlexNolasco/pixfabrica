export function ParamSegmentedEnum({
  value,
  options,
  optionLabels,
  onChange,
}: {
  value: string
  options: string[]
  optionLabels?: Record<string, string>
  onChange: (v: string) => void
}) {
  return (
    <div className="flex flex-wrap gap-0.5">
      {options.map((opt) => (
        <button
          key={opt}
          type="button"
          className={`rounded px-2 py-0.5 text-[10px] ${
            value === opt
              ? 'bg-primary/20 text-primary ring-1 ring-primary/40'
              : 'bg-muted/60 text-muted-foreground hover:bg-muted'
          }`}
          onClick={() => onChange(opt)}
        >
          {optionLabels?.[opt] ?? opt}
        </button>
      ))}
    </div>
  )
}
