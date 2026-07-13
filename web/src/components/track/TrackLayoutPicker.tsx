import { useMemo, type ReactNode } from 'react'
import {
  LayoutFillIcon,
  LayoutHorizontalIcon,
  LayoutVerticalIcon,
} from '@/components/track/TrackSettingIcons'
import { ImageOptionGrid, type ImageOption } from '@/components/track/ImageOptionGrid'
import { LAYOUT_OPTIONS, type LayoutOption } from '@/lib/trackVisualSettings'
import { useT, type TranslationKey } from '@/lib/i18n'
import type { Track } from '@/store/projectStore'

const LAYOUT_LABEL_KEYS: Record<LayoutOption, TranslationKey> = {
  fill: 'track_layout_fill',
  vertical: 'track_layout_vertical',
  horizontal: 'track_layout_horizontal',
}

const LAYOUT_ICONS: Record<LayoutOption, () => ReactNode> = {
  fill: LayoutFillIcon,
  vertical: LayoutVerticalIcon,
  horizontal: LayoutHorizontalIcon,
}

export function TrackLayoutPicker({
  track,
  onLayoutChange,
}: {
  track: Track
  onLayoutChange: (layout: LayoutOption) => void
}) {
  const t = useT()

  const options = useMemo((): ImageOption<LayoutOption>[] => {
    return LAYOUT_OPTIONS.map((id) => {
      const Icon = LAYOUT_ICONS[id]
      return {
        id,
        label: t(LAYOUT_LABEL_KEYS[id]),
        icon: <Icon />,
      }
    })
  }, [t])

  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-muted-foreground text-[11px] uppercase tracking-wide">{t('prop_layout')}</span>
      <ImageOptionGrid value={track.layout} options={options} onChange={onLayoutChange} columns={3} />
    </div>
  )
}
