const selectClass =
  'w-full rounded border border-border bg-background px-2 py-1 text-xs outline-none focus:border-primary/60'

export function ParamSelect({
  value,
  options,
  optionLabels,
  nullable,
  onChange,
}: {
  value: string | null
  options: string[]
  optionLabels?: Record<string, string>
  nullable?: boolean
  onChange: (v: string | null) => void
}) {
  return (
    <select
      className={selectClass}
      value={value ?? ''}
      onChange={(e) => {
        const v = e.target.value
        onChange(nullable && v === '' ? null : v)
      }}
    >
      {nullable ? <option value="">—</option> : null}
      {options.map((opt) => (
        <option key={opt} value={opt}>
          {optionLabels?.[opt] ?? opt}
        </option>
      ))}
    </select>
  )
}
