import { ArrowUpDown } from 'lucide-react'
import { Slider } from '@/components/ui/slider'
import {
  HEADER_FRACTION_SNAPS,
  headerFractionToSliderPercent,
  isSplitLayout,
  sliderPercentToHeaderFraction,
} from '@/lib/trackVisualSettings'
import { useT } from '@/lib/i18n'
import type { Track } from '@/store/projectStore'

function snapSliderPercent(percent: number): number {
  const snaps = HEADER_FRACTION_SNAPS.map((f) => Math.round(f * 100))
  let closest = snaps[0]!
  let bestDist = Math.abs(percent - closest)
  for (const snap of snaps) {
    const dist = Math.abs(percent - snap)
    if (dist < bestDist) {
      closest = snap
      bestDist = dist
    }
  }
  return bestDist <= 3 ? closest : percent
}

export function TrackBandLayoutControls({
  track,
  onHeaderFractionChange,
  onSwapClips,
}: {
  track: Track
  onHeaderFractionChange: (headerFraction: number | null) => void
  onSwapClips: () => void
}) {
  const t = useT()

  if (!isSplitLayout(track.layout) || track.clips.length !== 2) {
    return null
  }

  const sliderPercent = headerFractionToSliderPercent(track.headerFraction)
  const isEqual = track.headerFraction == null

  return (
    <div className="flex flex-col gap-1.5 rounded border border-border px-2 py-2">
      <div className="flex items-center justify-between gap-2">
        <span className="text-muted-foreground text-[11px] uppercase tracking-wide">
          {t('track_first_band_size')}
        </span>
        <span className="text-[10px] font-mono text-muted-foreground">
          {isEqual ? t('track_first_band_equal') : `${sliderPercent}%`}
        </span>
      </div>
      <Slider
        min={10}
        max={50}
        step={1}
        value={[sliderPercent]}
        onValueChange={(v) => {
          const n = Array.isArray(v) ? v[0] : v
          const snapped = snapSliderPercent(n ?? sliderPercent)
          onHeaderFractionChange(sliderPercentToHeaderFraction(snapped))
        }}
      />
      <p className="text-[10px] text-muted-foreground">{t('track_first_band_size_hint')}</p>
      <button
        type="button"
        className="inline-flex items-center justify-center gap-1.5 rounded border border-border px-2 py-1 text-[11px] text-muted-foreground hover:bg-muted/60 hover:text-foreground"
        onClick={onSwapClips}
      >
        <ArrowUpDown className="size-3" aria-hidden />
        {t('track_swap_clips')}
      </button>
    </div>
  )
}
