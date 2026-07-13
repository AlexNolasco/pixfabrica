import type { ReactNode } from 'react'

export function ParamField({
  label,
  description,
  children,
}: {
  label: string
  description?: string
  children: ReactNode
}) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-muted-foreground">{label}</span>
      {description ? (
        <p className="text-[10px] text-muted-foreground/80 leading-snug">{description}</p>
      ) : null}
      {children}
    </div>
  )
}
