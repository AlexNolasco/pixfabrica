import { ArrowDown, ArrowLeft, ArrowRight, ArrowUp } from 'lucide-react'
import { useMemo, type ReactNode } from 'react'
import { ImageOptionGrid, type ImageOption } from '@/components/track/ImageOptionGrid'
import {
  TransitionBlurIcon,
  TransitionFadeIcon,
  TransitionNoneIcon,
  TransitionScaleIcon,
  TransitionSlideIcon,
  TransitionWipeIcon,
} from '@/components/track/TrackSettingIcons'
import { useT, type TranslationKey } from '@/lib/i18n'
import { pauseTransportAt } from '@/lib/previewTransport'
import {
  applyTransitionGridChoice,
  DIRECTION_OPTIONS,
  EASING_OPTIONS,
  TRANSITION_TYPES,
  resolvedTrackDuration,
  transitionUsesDirection,
  type DirectionOption,
  type EasingOption,
  type TransitionTypeOption,
} from '@/lib/trackVisualSettings'
import type { Track, Transition } from '@/store/projectStore'

const TRANSITION_LABEL_KEYS: Record<TransitionTypeOption, TranslationKey> = {
  fade: 'track_transition_fade',
  slide: 'track_transition_slide',
  scale: 'track_transition_scale',
  blur: 'track_transition_blur',
  wipe: 'track_transition_wipe',
}

const TRANSITION_ICONS: Record<TransitionTypeOption, () => ReactNode> = {
  fade: TransitionFadeIcon,
  slide: TransitionSlideIcon,
  scale: TransitionScaleIcon,
  blur: TransitionBlurIcon,
  wipe: TransitionWipeIcon,
}

const EASING_LABEL_KEYS: Record<EasingOption, TranslationKey> = {
  linear: 'track_easing_linear',
  ease_in: 'track_easing_ease_in',
  ease_out: 'track_easing_ease_out',
  ease_in_out: 'track_easing_ease_in_out',
}

type GridChoice = 'none' | TransitionTypeOption

const DIRECTION_ICONS: Record<DirectionOption, typeof ArrowLeft> = {
  left: ArrowLeft,
  right: ArrowRight,
  up: ArrowUp,
  down: ArrowDown,
}

export function TrackTransitionPicker({
  sectionLabel,
  value,
  previewAtStartLabel,
  previewAtEndLabel,
  onChange,
  onPreviewAtStart,
  onPreviewAtEnd,
}: {
  sectionLabel: string
  value: Transition | undefined
  previewAtStartLabel: string
  previewAtEndLabel: string
  onChange: (next: Transition | undefined) => void
  onPreviewAtStart: () => void
  onPreviewAtEnd: () => void
}) {
  const t = useT()
  const gridValue: GridChoice = value?.type ?? 'none'

  const options = useMemo((): ImageOption<GridChoice>[] => {
    const none: ImageOption<GridChoice> = {
      id: 'none',
      label: t('prop_transition_none'),
      icon: <TransitionNoneIcon />,
    }
    const types = TRANSITION_TYPES.map((id): ImageOption<GridChoice> => {
      const Icon = TRANSITION_ICONS[id]
      return {
        id,
        label: t(TRANSITION_LABEL_KEYS[id]),
        icon: <Icon />,
      }
    })
    return [none, ...types]
  }, [t])

  const handleGridChange = (id: GridChoice) => {
    onChange(applyTransitionGridChoice(value, id))
  }

  const patch = (partial: Partial<Transition>) => {
    if (!value) return
    onChange({ ...value, ...partial })
  }

  const showDetails = value != null
  const showDirection = value != null && transitionUsesDirection(value.type)

  return (
    <div className="flex flex-col gap-1.5 rounded border border-border px-2 py-2">
      <span className="text-muted-foreground text-[11px] uppercase tracking-wide">{sectionLabel}</span>
      <ImageOptionGrid value={gridValue} options={options} onChange={handleGridChange} columns={3} />

      {showDetails ? (
        <div className="flex flex-col gap-2 pt-1 border-t border-border/60">
          <div className="flex items-center gap-2">
            <label className="shrink-0 text-muted-foreground w-14">{t('track_transition_duration')}</label>
            <input
              type="number"
              min={0.01}
              max={30}
              step={0.05}
              className="flex-1 rounded border border-border bg-background px-2 py-0.5 text-xs font-mono outline-none focus:border-primary/60"
              value={value.duration}
              onChange={(e) => {
                const n = Number.parseFloat(e.target.value)
                if (Number.isFinite(n)) patch({ duration: Math.min(30, Math.max(0.01, n)) })
              }}
            />
            <span className="text-muted-foreground text-[10px]">s</span>
          </div>
          <div className="flex flex-col gap-0.5">
            <span className="text-muted-foreground">{t('track_transition_easing')}</span>
            <select
              className="rounded border border-border bg-background px-2 py-1 text-xs outline-none focus:border-primary/60"
              value={value.easing}
              onChange={(e) => patch({ easing: e.target.value })}
            >
              {EASING_OPTIONS.map((opt) => (
                <option key={opt} value={opt}>
                  {t(EASING_LABEL_KEYS[opt])}
                </option>
              ))}
            </select>
          </div>
          {showDirection ? (
            <div className="flex flex-col gap-0.5">
              <span className="text-muted-foreground">{t('track_transition_direction')}</span>
              <div className="flex gap-1">
                {DIRECTION_OPTIONS.map((dir) => {
                  const Icon = DIRECTION_ICONS[dir]
                  const active = (value.direction ?? 'left') === dir
                  return (
                    <button
                      key={dir}
                      type="button"
                      title={t(`track_direction_${dir}` as TranslationKey)}
                      className={`flex-1 flex items-center justify-center rounded border py-1 ${
                        active
                          ? 'border-primary/50 bg-primary/15 text-primary'
                          : 'border-border text-muted-foreground hover:bg-accent'
                      }`}
                      onClick={() => patch({ direction: dir })}
                    >
                      <Icon className="h-3.5 w-3.5" />
                    </button>
                  )
                })}
              </div>
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="flex flex-wrap gap-x-3 gap-y-0.5 pt-0.5">
        <button
          type="button"
          className="text-[10px] text-primary hover:underline"
          onClick={onPreviewAtStart}
        >
          {previewAtStartLabel}
        </button>
        <button
          type="button"
          className="text-[10px] text-primary hover:underline"
          onClick={onPreviewAtEnd}
        >
          {previewAtEndLabel}
        </button>
      </div>
    </div>
  )
}

export function buildTransitionPreviewHandlers(
  track: Track,
  projectDuration: number,
  transition: Transition | undefined,
  kind: 'in' | 'out',
) {
  const duration = resolvedTrackDuration(track, projectDuration)
  return {
    onPreviewAtStart: () => pauseTransportAt(track.start),
    onPreviewAtEnd: () => {
      if (kind === 'out' && transition) {
        const outStart = track.start + duration - transition.duration
        pauseTransportAt(Math.max(track.start, outStart))
      } else {
        pauseTransportAt(track.start + duration)
      }
    },
  }
}
