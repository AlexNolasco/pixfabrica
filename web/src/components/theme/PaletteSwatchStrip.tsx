import { COLOR_TOKENS } from '@/lib/themeColor'
import type { JobColorPalette } from '@/lib/jobColors'

/** Compact horizontal strip of the 7 job color tokens. */
export function PaletteSwatchStrip({
  palette,
  size = 'sm',
}: {
  palette: JobColorPalette
  size?: 'sm' | 'xs'
}) {
  const cell = size === 'sm' ? 'h-3 w-3' : 'h-2.5 w-2.5'
  return (
    <span
      className="inline-flex shrink-0 overflow-hidden rounded border border-border"
      aria-hidden
    >
      {COLOR_TOKENS.map((token) => (
        <span
          key={token}
          className={cell}
          style={{ backgroundColor: palette[token] }}
          title={token}
        />
      ))}
    </span>
  )
}
