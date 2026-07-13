import { Check, LayoutGrid, List, Plus, X } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  buildCatalogDisplay,
  categoryTranslationKey,
  readCatalogViewMode,
  tagTranslationKey,
  writeCatalogViewMode,
  type CatalogViewMode,
} from '@/lib/catalogDisplay'
import { catalogEffectType } from '@/lib/catalogDetail'
import { useT } from '@/lib/i18n'
import { canAddClipToTrack } from '@/lib/projectLimits'
import {
  useProjectStore,
  type CatalogEffectItem,
  type CatalogClipItem,
} from '@/store/projectStore'

const TRACK_BADGE: Record<string, string> = {
  skia: 'bg-blue-500/20 text-blue-400',
  gl: 'bg-purple-500/20 text-purple-400',
  post: 'bg-orange-500/20 text-orange-400',
}

const ACK_MS = 1500

function ClipIcon({ svg }: { svg: string }) {
  return (
    <span
      className="h-8 w-8 shrink-0 text-foreground [&>svg]:h-full [&>svg]:w-full"
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  )
}

function CatalogSkeleton() {
  return (
    <div className="flex flex-col gap-2">
      {Array.from({ length: 6 }, (_, i) => (
        <div key={i} className="h-12 rounded-md bg-muted animate-pulse" />
      ))}
    </div>
  )
}

function CatalogRow({
  clip,
  viewMode,
  showAdded,
  onDisabledHint,
  onAdd,
  limitBlocked = false,
}: {
  clip: CatalogClipItem
  viewMode: CatalogViewMode
  showAdded: boolean
  onDisabledHint: string
  onAdd: () => void
  limitBlocked?: boolean
}) {
  const t = useT()
  const disabled = clip.disabled || limitBlocked

  const addControl = disabled ? null : showAdded ? (
    <span className="flex items-center gap-0.5 text-[10px] text-primary shrink-0">
      <Check className="h-3 w-3" />
      {t('catalog_row_added')}
    </span>
  ) : (
    <button
      type="button"
      className="shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium text-primary hover:bg-primary/15 opacity-0 group-hover:opacity-100 focus:opacity-100"
      onClick={(e) => {
        e.stopPropagation()
        onAdd()
      }}
    >
      {t('catalog_row_add')}
    </button>
  )

  const rowMuted = disabled ? 'opacity-45' : ''
  const rowHover = disabled ? 'cursor-not-allowed' : 'group hover:bg-accent/60'

  if (viewMode === 'icons') {
    return (
      <div
        className={`relative group flex flex-col items-center gap-1 p-2 text-center rounded-md border border-border transition-colors ${rowHover} ${rowMuted}`}
        title={disabled ? onDisabledHint : clip.description}
      >
        <ClipIcon svg={clip.icon} />
        <span className="text-[10px] leading-tight line-clamp-2">{clip.label}</span>
        {!disabled && (
          <div className="absolute top-1 right-1">
            {showAdded ? (
              <span className="flex h-5 w-5 items-center justify-center rounded-full bg-primary/20 text-primary">
                <Check className="h-3 w-3" />
              </span>
            ) : (
              <button
                type="button"
                className="flex h-5 w-5 items-center justify-center rounded-full bg-background/90 border border-border text-muted-foreground hover:text-primary hover:border-primary/40 opacity-0 group-hover:opacity-100"
                title={t('catalog_row_add')}
                onClick={(e) => {
                  e.stopPropagation()
                  onAdd()
                }}
              >
                <Plus className="h-3 w-3" />
              </button>
            )}
          </div>
        )}
      </div>
    )
  }

  return (
    <div
      className={`group flex gap-2 p-2 rounded-md border border-border transition-colors ${rowHover} ${rowMuted}`}
      title={disabled ? onDisabledHint : undefined}
    >
      <ClipIcon svg={clip.icon} />
      <div className="min-w-0 flex-1">
        <div className="text-xs font-medium truncate">{clip.label}</div>
        <p className="text-[10px] text-muted-foreground line-clamp-2 leading-snug">
          {clip.description}
        </p>
        {disabled && (
          <p className="text-[10px] text-muted-foreground mt-0.5">{onDisabledHint}</p>
        )}
      </div>
      {addControl}
    </div>
  )
}

const EFFECT_BACKEND_BADGE: Record<string, string> = {
  skia: 'bg-blue-500/20 text-blue-400',
  gl: 'bg-purple-500/20 text-purple-400',
  raster: 'bg-orange-500/20 text-orange-400',
}

function effectBackendLabel(backend: string): string {
  if (backend === 'gl') return 'GL'
  if (backend === 'skia') return 'Skia'
  return backend
}

function EffectCatalogRow({
  effect,
  disabled,
  disabledHint,
  onAdd,
}: {
  effect: CatalogEffectItem
  disabled?: boolean
  disabledHint?: string
  onAdd: () => void
}) {
  const badgeClass = EFFECT_BACKEND_BADGE[effect.effect_backend] ?? EFFECT_BACKEND_BADGE.skia
  const rowMuted = disabled ? 'opacity-45' : ''
  const rowHover = disabled ? 'cursor-not-allowed' : 'group hover:bg-accent/60'

  return (
    <div
      className={`group flex gap-2 p-2 rounded-md border border-border ${rowHover} ${rowMuted}`}
      title={disabled ? disabledHint : undefined}
    >
      <span
        className="h-8 w-8 shrink-0 text-foreground [&>svg]:h-full [&>svg]:w-full"
        dangerouslySetInnerHTML={{ __html: effect.icon }}
      />
      <div className="min-w-0 flex-1">
        <div className="text-xs font-medium truncate flex items-center gap-1.5">
          <span className="truncate">{effect.label}</span>
          <span className={`text-[9px] font-semibold px-1 rounded shrink-0 ${badgeClass}`}>
            {effectBackendLabel(effect.effect_backend)}
          </span>
        </div>
        <p className="text-[10px] text-muted-foreground line-clamp-2 leading-snug">
          {effect.description}
        </p>
        {disabled && disabledHint ? (
          <p className="text-[10px] text-muted-foreground mt-0.5 leading-snug">{disabledHint}</p>
        ) : null}
      </div>
      {disabled ? null : (
        <button
          type="button"
          className="shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium text-primary hover:bg-primary/15 opacity-0 group-hover:opacity-100 focus:opacity-100"
          onClick={onAdd}
        >
          Add
        </button>
      )}
    </div>
  )
}

export function PluginCatalogPane() {
  const t = useT()
  const pluginPicker = useProjectStore((s) => s.pluginPicker)
  const tracks = useProjectStore((s) => s.tracks)
  const catalogClips = useProjectStore((s) => s.catalogClips)
  const catalogEffects = useProjectStore((s) => s.catalogEffects)
  const catalogLoadStatus = useProjectStore((s) => s.catalogLoadStatus)
  const catalogSearchByKind = useProjectStore((s) => s.catalogSearchByKind)
  const catalogAddFeedback = useProjectStore((s) => s.catalogAddFeedback)
  const setCatalogSearch = useProjectStore((s) => s.setCatalogSearch)
  const closePluginPicker = useProjectStore((s) => s.closePluginPicker)
  const addCatalogClip = useProjectStore((s) => s.addCatalogClip)
  const addCatalogEffect = useProjectStore((s) => s.addCatalogEffect)
  const addCatalogTrackEffect = useProjectStore((s) => s.addCatalogTrackEffect)
  const clearCatalogAddFeedback = useProjectStore((s) => s.clearCatalogAddFeedback)
  const serverConfig = useProjectStore((s) => s.serverConfig)

  const [viewMode, setViewMode] = useState<CatalogViewMode>(() => readCatalogViewMode())
  const [effectSearch, setEffectSearch] = useState('')

  const isEffectMode = pluginPicker?.mode === 'effect'
  const isTrackEffectMode = isEffectMode && pluginPicker?.effectScope === 'track'
  const trackKind = pluginPicker?.trackKind ?? 'skia'
  const searchQuery = isEffectMode ? effectSearch : catalogSearchByKind[trackKind]
  const track = tracks.find((tr) => tr.id === pluginPicker?.trackId)
  const clip =
    isEffectMode && !isTrackEffectMode && pluginPicker?.clipId
      ? track?.clips.find((el) => el.id === pluginPicker.clipId)
      : undefined
  const canAddClip = track ? canAddClipToTrack(track, serverConfig) : false
  const canAddEffect = isTrackEffectMode
    ? (track?.effects?.length ?? 0) < 3
    : (clip?.effects?.length ?? 0) < 3

  useEffect(() => {
    if (!catalogAddFeedback) return
    const timer = window.setTimeout(() => clearCatalogAddFeedback(), ACK_MS)
    return () => window.clearTimeout(timer)
  }, [catalogAddFeedback, clearCatalogAddFeedback])

  const handleAdd = useCallback(
    (clip: CatalogClipItem) => {
      if (!pluginPicker || clip.disabled || !canAddClip) return
      addCatalogClip(pluginPicker.trackId, clip.clip_type, clip.label)
    },
    [addCatalogClip, canAddClip, pluginPicker],
  )

  const filteredEffects = useMemo(() => {
    const q = effectSearch.trim().toLowerCase()
    const lockedBackend = isTrackEffectMode
      ? ('gl' as const)
      : pluginPicker?.effectBackend

    return catalogEffects
      .filter((effect) => !effect.disabled)
      .filter((effect) => {
        if (!q) return true
        return (
          effect.label.toLowerCase().includes(q) ||
          catalogEffectType(effect).toLowerCase().includes(q) ||
          effect.description.toLowerCase().includes(q)
        )
      })
      .map((effect) => {
        let incompatible = false
        let incompatibleHint: string | undefined
        if (isTrackEffectMode && effect.effect_backend !== 'gl') {
          incompatible = true
          incompatibleHint = t('prop_effects_track_gl_only')
        } else if (lockedBackend && effect.effect_backend !== lockedBackend) {
          incompatible = true
          incompatibleHint = t('prop_effects_backend_locked')
            .replace('{required}', effectBackendLabel(effect.effect_backend))
            .replace('{locked}', effectBackendLabel(lockedBackend))
        }
        return { effect, incompatible, incompatibleHint }
      })
  }, [catalogEffects, effectSearch, isTrackEffectMode, pluginPicker?.effectBackend, t])

  const handleAddEffect = useCallback(
    (effect: CatalogEffectItem) => {
      if (!pluginPicker || !canAddEffect) return
      if (isTrackEffectMode) {
        addCatalogTrackEffect(pluginPicker.trackId, catalogEffectType(effect), effect.label)
        return
      }
      if (!pluginPicker.clipId) return
      addCatalogEffect(
        pluginPicker.trackId,
        pluginPicker.clipId,
        catalogEffectType(effect),
        effect.label,
      )
    },
    [addCatalogEffect, addCatalogTrackEffect, canAddEffect, isTrackEffectMode, pluginPicker],
  )

  const resolveTagLabel = useCallback(
    (tag: string) => {
      const key = tagTranslationKey(tag)
      const translated = t(key)
      return translated === key ? tag.replace(/_/g, ' ') : translated
    },
    [t],
  )

  const { sections, flat } = useMemo(
    () =>
      buildCatalogDisplay(catalogClips, trackKind, searchQuery, resolveTagLabel),
    [catalogClips, trackKind, searchQuery, resolveTagLabel],
  )

  const onViewModeChange = (mode: CatalogViewMode) => {
    setViewMode(mode)
    writeCatalogViewMode(mode)
  }

  const trackType = track?.trackType ?? trackKind
  const badgeClass = TRACK_BADGE[trackType] ?? TRACK_BADGE.skia

  const loading = catalogLoadStatus === 'idle' || catalogLoadStatus === 'loading'
  const showEmpty = !loading && (isEffectMode ? filteredEffects.length === 0 : flat.length === 0)

  if (isEffectMode) {
    return (
      <div data-transport-block className="flex flex-col h-full text-xs">
        <div className="px-3 py-2 border-b border-border shrink-0 space-y-2">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <h2 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                {t('prop_effects_add')}
              </h2>
              {clip ? (
                <p className="text-xs truncate mt-0.5">{clip.label}</p>
              ) : null}
            </div>
            <button
              type="button"
              className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground shrink-0"
              onClick={closePluginPicker}
              title={t('catalog_cancel')}
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <input
            type="search"
            className="w-full rounded border border-border bg-background px-2 py-1 text-xs outline-none focus:border-primary/60"
            placeholder={t('catalog_search_placeholder')}
            value={effectSearch}
            onChange={(e) => setEffectSearch(e.target.value)}
          />
        </div>
        <div className="flex-1 overflow-y-auto p-3 mb-4">
          {loading && <CatalogSkeleton />}
          {showEmpty && (
            <p className="text-muted-foreground text-center py-6">{t('catalog_no_results')}</p>
          )}
          {!loading && !showEmpty && (
            <div className="flex flex-col gap-1">
              {filteredEffects.map(({ effect, incompatible, incompatibleHint }) => (
                <EffectCatalogRow
                  key={catalogEffectType(effect)}
                  effect={effect}
                  disabled={incompatible}
                  disabledHint={incompatibleHint}
                  onAdd={() => handleAddEffect(effect)}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    )
  }

  const rowProps = (clip: CatalogClipItem) => ({
    clip,
    showAdded: catalogAddFeedback?.clipType === clip.clip_type,
    limitBlocked: !canAddClip,
    onDisabledHint: !canAddClip
      ? t('limit_timeline_add_clip_full').replace('{max}', String(serverConfig.maxClipsPerTrack))
      : clip.restricted_reason === 'license'
        ? t('catalog_license_disabled').replace('{license}', clip.license)
        : t('catalog_plugin_disabled'),
    onAdd: () => handleAdd(clip),
  })

  const showLicensePolicyBanner =
    !isEffectMode && serverConfig.catalogExcludedLicenses.length > 0

  return (
    <div data-transport-block className="flex flex-col h-full text-xs">
      <div className="px-3 py-2 border-b border-border shrink-0 space-y-2">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <h2 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              {t('catalog_add_plugin')}
            </h2>
            {track && (
              <p className="text-xs truncate mt-0.5 flex items-center gap-1.5">
                <span className={`text-[9px] font-semibold px-1 rounded shrink-0 ${badgeClass}`}>
                  {trackType === 'skia' ? 'Skia' : trackType === 'gl' ? 'GL' : 'Post'}
                </span>
                <span className="truncate">{track.label}</span>
              </p>
            )}
          </div>
          <button
            type="button"
            className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground shrink-0"
            onClick={closePluginPicker}
            title={t('catalog_cancel')}
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex items-center gap-1">
          <input
            type="search"
            className="flex-1 min-w-0 rounded border border-border bg-background px-2 py-1 text-xs outline-none focus:border-primary/60"
            placeholder={t('catalog_search_placeholder')}
            value={searchQuery}
            onChange={(e) => setCatalogSearch(trackKind, e.target.value)}
          />
          {searchQuery.trim() !== '' && (
            <button
              type="button"
              className="shrink-0 rounded px-2 py-1 text-[11px] text-muted-foreground hover:bg-accent hover:text-foreground"
              onClick={() => setCatalogSearch(trackKind, '')}
            >
              {t('catalog_clear_search')}
            </button>
          )}
          <button
            type="button"
            className={`rounded p-1 ${viewMode === 'list' ? 'bg-primary/15 text-primary' : 'text-muted-foreground hover:bg-accent'}`}
            title={t('catalog_view_list')}
            onClick={() => onViewModeChange('list')}
          >
            <List className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            className={`rounded p-1 ${viewMode === 'icons' ? 'bg-primary/15 text-primary' : 'text-muted-foreground hover:bg-accent'}`}
            title={t('catalog_view_icons')}
            onClick={() => onViewModeChange('icons')}
          >
            <LayoutGrid className="h-3.5 w-3.5" />
          </button>
        </div>
        {showLicensePolicyBanner && (
          <p className="text-[10px] text-muted-foreground leading-snug">
            {t('catalog_license_policy_banner')}
          </p>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-3 mb-4">
        {loading && <CatalogSkeleton />}
        {showEmpty && (
          <p className="text-muted-foreground text-center py-6">{t('catalog_no_results')}</p>
        )}
        {!loading && !showEmpty && viewMode === 'icons' && (
          <div className="grid grid-cols-3 gap-2">
            {flat.map((clip) => (
              <CatalogRow
                key={clip.clip_type}
                viewMode="icons"
                {...rowProps(clip)}
              />
            ))}
          </div>
        )}
        {!loading && !showEmpty && viewMode === 'list' && (
          <div className="flex flex-col gap-3">
            {sections.map((section) => (
              <section key={section.category || 'flat'}>
                {section.category && searchQuery.trim() === '' && (
                  <h3 className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1.5 px-0.5">
                    {section.category === '__pinned__'
                      ? t('catalog_section_pinned')
                      : t(categoryTranslationKey(section.category))}
                  </h3>
                )}
                <div className="flex flex-col gap-1">
                  {section.clips.map((clip) => (
                    <CatalogRow
                      key={clip.clip_type}
                      viewMode="list"
                      {...rowProps(clip)}
                    />
                  ))}
                </div>
              </section>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
