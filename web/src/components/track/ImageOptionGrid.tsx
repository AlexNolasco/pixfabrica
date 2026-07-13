import type { ReactNode } from 'react'

export type ImageOption<T extends string> = {
  id: T
  label: string
  icon: ReactNode
}

export function ImageOptionGrid<T extends string>({
  value,
  options,
  onChange,
  columns = 3,
}: {
  value: T
  options: ImageOption<T>[]
  onChange: (id: T) => void
  columns?: 2 | 3
}) {
  return (
    <div
      className={columns === 3 ? 'grid grid-cols-3 gap-1.5' : 'grid grid-cols-2 gap-1.5'}
      role="radiogroup"
    >
      {options.map((opt) => {
        const selected = value === opt.id
        return (
          <button
            key={opt.id}
            type="button"
            role="radio"
            aria-checked={selected}
            className={`group flex flex-col items-center gap-1 rounded-md border px-1 py-1.5 transition-colors ${
              selected
                ? 'border-primary/50 bg-primary/15 ring-1 ring-primary/40'
                : 'border-border bg-muted/30 hover:border-primary/30 hover:bg-accent/40'
            }`}
            onClick={() => onChange(opt.id)}
          >
            <span className="flex h-9 w-full items-center justify-center overflow-hidden rounded-sm bg-background/50 px-0.5">
              {opt.icon}
            </span>
            <span className="w-full truncate text-center text-[9px] leading-tight text-muted-foreground group-hover:text-foreground">
              {opt.label}
            </span>
          </button>
        )
      })}
    </div>
  )
}
