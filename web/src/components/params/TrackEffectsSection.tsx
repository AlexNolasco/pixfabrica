import { ChevronDown, ChevronUp, Plus, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { DynamicClipForm } from '@/components/params/DynamicClipForm'
import { Button } from '@/components/ui/button'
import { catalogDetailCacheKey, catalogEffectType } from '@/lib/catalogDetail'
import { useT } from '@/lib/i18n'
import { useProjectStore, type Track } from '@/store/projectStore'

const MAX_EFFECTS = 3

export function TrackEffectsSection({ track }: { track: Track }) {
  const t = useT()
  const locale = useProjectStore((s) => s.appSettings.locale)
  const catalogDetailCache = useProjectStore((s) => s.catalogDetailCache)
  const catalogEffects = useProjectStore((s) => s.catalogEffects)
  const openTrackEffectPicker = useProjectStore((s) => s.openTrackEffectPicker)
  const reorderTrackEffects = useProjectStore((s) => s.reorderTrackEffects)
  const toggleTrackEffectEnabled = useProjectStore((s) => s.toggleTrackEffectEnabled)
  const removeTrackEffect = useProjectStore((s) => s.removeTrackEffect)
  const ensureCatalogDetail = useProjectStore((s) => s.ensureCatalogDetail)

  const effects = track.effects ?? []
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [sectionOpen, setSectionOpen] = useState(effects.length > 0)

  useEffect(() => {
    for (const fx of effects) {
      void ensureCatalogDetail(fx.effect_type, 'effect')
    }
  }, [effects, ensureCatalogDetail])

  const chainBackend = (() => {
    const active = effects.filter((fx) => fx.enabled !== false)
    if (active.length === 0) return undefined
    return catalogEffects.find(
      (c) => catalogEffectType(c) === active[0].effect_type,
    )?.effect_backend
  })()

  const canAdd = effects.length < MAX_EFFECTS

  return (
    <div className="flex flex-col gap-1 rounded border border-border px-2 py-2">
      <button
        type="button"
        className="flex items-center justify-between gap-2 text-left"
        onClick={() => setSectionOpen((v) => !v)}
      >
        <span className="text-muted-foreground text-[11px] uppercase tracking-wide">
          {t('prop_track_effects')} ({effects.length}/{MAX_EFFECTS})
        </span>
        <ChevronDown
          className={`h-3.5 w-3.5 text-muted-foreground transition-transform ${sectionOpen ? 'rotate-180' : ''}`}
        />
      </button>
      {sectionOpen ? (
        <>
          <p className="text-[10px] text-muted-foreground leading-snug">
            {t('prop_track_effects_hint')}
          </p>
          {effects.length === 0 ? (
            <p className="text-[10px] text-muted-foreground italic">
              {t('prop_effects_empty')}
            </p>
          ) : (
            <ul className="flex flex-col gap-0.5">
              {effects.map((fx, index) => {
                const label =
                  catalogEffects.find((c) => catalogEffectType(c) === fx.effect_type)?.label ??
                  fx.label ??
                  fx.effect_type
                const expanded = expandedId === fx.id
                const cacheKey = catalogDetailCacheKey(fx.effect_type, locale)
                const detail = catalogDetailCache[cacheKey]
                return (
                  <li
                    key={fx.id}
                    className={`rounded px-1 py-0.5 ${expanded ? 'bg-primary/10 ring-1 ring-primary/25' : 'bg-muted/50'}`}
                  >
                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        className="flex-1 truncate text-left text-foreground text-[11px]"
                        onClick={() => setExpandedId(expanded ? null : fx.id)}
                      >
                        {label}
                      </button>
                      <button
                        type="button"
                        className={`rounded px-1.5 py-0.5 text-[10px] ${
                          fx.enabled !== false
                            ? 'bg-primary/15 text-primary'
                            : 'bg-muted text-muted-foreground'
                        }`}
                        onClick={() => toggleTrackEffectEnabled(track.id, fx.id)}
                      >
                        {fx.enabled !== false ? t('prop_on') : t('prop_off')}
                      </button>
                      <button
                        type="button"
                        className="rounded p-0.5 hover:bg-accent disabled:opacity-30"
                        disabled={index <= 0}
                        title={t('prop_effects_move_up')}
                        onClick={() => reorderTrackEffects(track.id, index, index - 1)}
                      >
                        <ChevronUp className="h-3.5 w-3.5" />
                      </button>
                      <button
                        type="button"
                        className="rounded p-0.5 hover:bg-accent disabled:opacity-30"
                        disabled={index >= effects.length - 1}
                        title={t('prop_effects_move_down')}
                        onClick={() => reorderTrackEffects(track.id, index, index + 1)}
                      >
                        <ChevronDown className="h-3.5 w-3.5" />
                      </button>
                      <button
                        type="button"
                        className="rounded p-0.5 hover:bg-accent text-muted-foreground hover:text-destructive"
                        title={t('prop_effects_remove')}
                        onClick={() => removeTrackEffect(track.id, fx.id)}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                    {expanded && detail ? (
                      <div className="pt-2 pb-1">
                        <DynamicClipForm
                          detail={detail}
                          params={fx.params}
                          trackId={track.id}
                          trackEffectId={fx.id}
                        />
                      </div>
                    ) : null}
                  </li>
                )
              })}
            </ul>
          )}
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="w-full mt-1"
            disabled={!canAdd}
            onClick={() => openTrackEffectPicker(track.id, chainBackend)}
          >
            <Plus className="h-3.5 w-3.5" />
            {canAdd ? t('prop_effects_add') : t('prop_effects_max')}
          </Button>
        </>
      ) : null}
    </div>
  )
}
