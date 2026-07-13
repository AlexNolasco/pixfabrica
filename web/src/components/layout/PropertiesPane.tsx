import { ChevronDown, ChevronUp, MoreHorizontal, Plus } from 'lucide-react'
import { isClipSelection } from '@/lib/selection'
import { useEffect, useState, type ReactNode } from 'react'
import { DynamicClipForm } from '@/components/params/DynamicClipForm'
import { useIsClipBroken } from '@/lib/brokenClips'
import { Button } from '@/components/ui/button'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { TrackLayoutPicker } from '@/components/track/TrackLayoutPicker'
import { TrackBandLayoutControls } from '@/components/track/TrackBandLayoutControls'
import { bandLayoutPatchForLayoutChange } from '@/lib/trackVisualSettings'
import {
  TrackTransitionPicker,
  buildTransitionPreviewHandlers,
} from '@/components/track/TrackTransitionPicker'
import { SoundPropertiesForm } from '@/components/sound/SoundPropertiesForm'
import { catalogKindForTrack, trackAcceptsCatalogClips } from '@/lib/catalogDisplay'
import {
  buildClipParamsExport,
  humanizeClipType,
  serializeClipParamsExport,
} from '@/lib/clipParamsExport'
import {
  mergeImportedClipParams,
  parseClipParamsClipboard,
  validateClipParamsIdentity,
  type ImportClipParamsError,
  type ImportClipParamsReport,
} from '@/lib/clipParamsImport'
import { catalogDetailCacheKey, type ClipCatalogLabels } from '@/lib/catalogDetail'
import { trackShowsEffects, trackShowsLayout, trackShowsTransitions } from '@/lib/trackVisualSettings'
import { useProjectStore, type Clip, type ProjectSetting, type Track } from '@/store/projectStore'
import { schedulePreviewRefresh } from '@/lib/previewRefresh'
import { useT } from '@/lib/i18n'
import { ClipEffectsSection } from '@/components/params/ClipEffectsSection'
import { TrackEffectsSection } from '@/components/params/TrackEffectsSection'
import { VideoFitDuration } from '@/components/video/VideoFitDuration'
import { VideoOptimizedBanner } from '@/components/video/VideoOptimizedBanner'
import { BackgroundImageExtractTheme } from '@/components/theme/BackgroundImageExtractTheme'
import { BACKGROUND_IMAGE_CLIP_TYPE } from '@/lib/timelineDrop/imageDrop'

export function PropertiesPane() {
  const t = useT()
  const selection = useProjectStore((s) => s.selection)
  const tracks = useProjectStore((s) => s.tracks)
  const sounds = useProjectStore((s) => s.sounds)
  const projectSettings = useProjectStore((s) => s.projectSettings)
  const updateTrack = useProjectStore((s) => s.updateTrack)
  const swapTrackClips = useProjectStore((s) => s.swapTrackClips)
  const toggleTrackEnabled = useProjectStore((s) => s.toggleTrackEnabled)
  const toggleClipEnabled = useProjectStore((s) => s.toggleClipEnabled)
  const reorderClips = useProjectStore((s) => s.reorderClips)
  const openPluginPicker = useProjectStore((s) => s.openPluginPicker)
  const setLayoutPrefs = useProjectStore((s) => s.setLayoutPrefs)
  const select = useProjectStore((s) => s.select)
  const isPlaying = useProjectStore((s) => s.isPlaying)
  const meta = useProjectStore((s) => s.meta)

  let title = t('prop_title')
  let headerActions: ReactNode = null
  let content: ReactNode = (
    <p className="text-xs text-muted-foreground">{t('prop_empty')}</p>
  )
  let selectedTrack: Track | null = null

  if (selection?.kind === 'projectSetting') {
    const setting = projectSettings.find((n) => n.id === selection.projectSettingId)
    if (setting) {
      title = setting.label
      content = (
        <div className="flex flex-col gap-2">
          <Field label={t('prop_type')} value={setting.clip_type} mono />
          <ClipUnavailableBanner clipType={setting.clip_type} />
          <ProjectSettingParamsEditor setting={setting} />
        </div>
      )
    }
  } else if (selection?.kind === 'sound') {
    const sound = sounds.find((s) => s.id === selection.soundId)
    if (sound) {
      title = sound.bus || t('sound_untitled')
      content = <SoundPropertiesForm sound={sound} allSounds={sounds} />
    }
  } else if (selection?.kind === 'track') {
    const track = tracks.find((t) => t.id === selection.trackId)
    if (track) {
      selectedTrack = track
      title = track.label
      content = (
        <div className="flex flex-col gap-2">
          <TrackDrawOrder
            track={track}
            highlightedClipId={null}
            reorderClips={reorderClips}
          />
          {(track.trackType ?? 'skia') === 'post' && track.clips.length === 0 ? (
            <p className="text-[10px] text-muted-foreground rounded border border-dashed border-border px-2 py-2">
              {t('prop_no_post_effect')}
            </p>
          ) : null}
          <div className="flex items-center justify-between rounded border border-border px-2 py-1.5">
            <span className="text-muted-foreground">{t('prop_enabled')}</span>
            <button
              type="button"
              className={`rounded px-2 py-0.5 text-[11px] ${
                track.enabled
                  ? 'bg-primary/15 text-primary hover:bg-primary/20'
                  : 'bg-muted text-muted-foreground hover:bg-muted/80'
              }`}
              onClick={() => toggleTrackEnabled(track.id)}
            >
              {track.enabled ? t('prop_on') : t('prop_off')}
            </button>
          </div>
          <Field label={t('prop_start')} value={`${track.start}s`} />
          <Field label={t('left_duration')} value={track.duration != null ? `${track.duration}s` : t('prop_inherited')} />
          {trackShowsLayout(track.trackType) ? (
            <>
              <TrackLayoutPicker
                track={track}
                onLayoutChange={(layout) =>
                  updateTrack(track.id, {
                    layout,
                    ...bandLayoutPatchForLayoutChange(
                      layout,
                      track.clips.length,
                      track.headerFraction,
                    ),
                  })
                }
              />
              <TrackBandLayoutControls
                track={track}
                onHeaderFractionChange={(headerFraction) =>
                  updateTrack(track.id, { headerFraction })
                }
                onSwapClips={() => swapTrackClips(track.id)}
              />
            </>
          ) : null}
          {trackShowsTransitions(track.trackType) ? (
            <>
              <TrackTransitionPicker
                sectionLabel={t('prop_transition_in')}
                value={track.transition_in}
                previewAtStartLabel={t('track_preview_at_start')}
                previewAtEndLabel={t('track_preview_at_end')}
                onChange={(transition_in) => updateTrack(track.id, { transition_in })}
                {...buildTransitionPreviewHandlers(
                  track,
                  meta.duration,
                  track.transition_in,
                  'in',
                )}
              />
              <TrackTransitionPicker
                sectionLabel={t('prop_transition_out')}
                value={track.transition_out}
                previewAtStartLabel={t('track_preview_at_start')}
                previewAtEndLabel={t('track_preview_at_end')}
                onChange={(transition_out) => updateTrack(track.id, { transition_out })}
                {...buildTransitionPreviewHandlers(
                  track,
                  meta.duration,
                  track.transition_out,
                  'out',
                )}
              />
            </>
          ) : null}
          {trackShowsEffects(track.trackType) ? (
            <TrackEffectsSection track={track} />
          ) : null}
        </div>
      )
    }
  } else if (isClipSelection(selection)) {
    const track = tracks.find((t) => t.id === selection.trackId)
    const clip = track?.clips.find((e) => e.id === selection.clipId)
    if (clip && track) {
      title = clip.label
      headerActions = <ClipPropertiesMenu trackId={track.id} clip={clip} />
      content = (
        <div className="flex flex-col gap-2">
          <TrackDrawOrder
            track={track}
            highlightedClipId={selection.clipId}
            reorderClips={reorderClips}
          />
          <div className="flex items-center justify-between rounded border border-border px-2 py-1.5">
            <span className="text-muted-foreground">{t('prop_enabled')}</span>
            <button
              type="button"
              className={`rounded px-2 py-0.5 text-[11px] ${
                clip.enabled
                  ? 'bg-primary/15 text-primary hover:bg-primary/20'
                  : 'bg-muted text-muted-foreground hover:bg-muted/80'
              }`}
              onClick={() => toggleClipEnabled(track.id, clip.id)}
            >
              {clip.enabled ? t('prop_on') : t('prop_off')}
            </button>
          </div>
          <Field label={t('prop_type')} value={clip.clip_type} mono />
          <Field label={t('prop_start')} value={`${clip.start}s`} />
          <Field label={t('left_duration')} value={clip.duration != null ? `${clip.duration}s` : t('prop_inherited')} />
          {(track.trackType ?? 'skia') !== 'post' ? (
            <ClipEffectsSection trackId={track.id} clip={clip} />
          ) : null}
          <ClipUnavailableBanner clipType={clip.clip_type} />
          <ClipParamsEditor
            trackId={track.id}
            clip={clip}
          />
        </div>
      )
    }
  }

  const showAddNodes =
    selectedTrack != null &&
    trackAcceptsCatalogClips(selectedTrack.trackType, selectedTrack.enabled ?? true)
  const isPostTrack = (selectedTrack?.trackType ?? 'skia') === 'post'
  const postHasEffect = (selectedTrack?.clips.length ?? 0) > 0
  const addButtonLabel = isPostTrack
    ? postHasEffect
      ? t('prop_change_effect')
      : t('prop_set_effect')
    : t('prop_add_clips')

  return (
    <div data-transport-block className="flex flex-col h-full text-xs">
      <div className="px-3 py-2 border-b border-border shrink-0 flex items-center justify-between gap-2">
        <h2 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground truncate min-w-0">
          {title}
        </h2>
        {headerActions}
      </div>
      <div className="flex-1 overflow-y-auto px-3 pt-3 pb-3">{content}</div>
      {showAddNodes ? (
        <div className="shrink-0 border-t border-border px-3 py-3">
          <Button
            type="button"
            className="w-full"
            disabled={isPlaying}
            onClick={() => {
              if (!selectedTrack) return
              select({ kind: 'track', trackId: selectedTrack.id })
              openPluginPicker(
                selectedTrack.id,
                catalogKindForTrack(selectedTrack.trackType),
              )
              setLayoutPrefs({ rightCollapsed: false })
            }}
          >
            <Plus />
            {addButtonLabel}
          </Button>
        </div>
      ) : null}
    </div>
  )
}

function TrackDrawOrder({
  track,
  highlightedClipId,
  reorderClips,
}: {
  track: Track
  highlightedClipId: string | null
  reorderClips: (trackId: string, fromIndex: number, toIndex: number) => void
}) {
  const t = useT()
  const n = track.clips.length
  const isPostTrack = (track.trackType ?? 'skia') === 'post'
  if (n === 0) {
    return (
      <p className="text-[10px] text-muted-foreground rounded border border-dashed border-border px-2 py-2">
        {t('prop_no_clips')}
      </p>
    )
  }
  const rows = track.clips.map((el, i) => ({ el, i })).reverse()
  return (
    <div className="flex flex-col gap-1 rounded border border-border px-2 py-2">
      <span className="text-muted-foreground text-[11px] uppercase tracking-wide">{t('prop_draw_order')}</span>
      <p className="text-[10px] text-muted-foreground leading-snug">{t('prop_draw_order_desc')}</p>
      <ul className="flex flex-col gap-0.5">
        {rows.map(({ el, i }) => (
          <li
            key={el.id}
            className={`flex items-center gap-1 rounded px-1 py-0.5 ${
              highlightedClipId === el.id ? 'bg-primary/15 ring-1 ring-primary/30' : 'bg-muted/50'
            }`}
          >
            <span className="flex-1 truncate text-foreground">{el.label}</span>
            <button
              type="button"
              className="rounded p-0.5 hover:bg-accent disabled:opacity-30"
              disabled={isPostTrack || i >= n - 1}
              title={t('prop_bring_forward')}
              onClick={() => reorderClips(track.id, i, i + 1)}
            >
              <ChevronUp className="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              className="rounded p-0.5 hover:bg-accent disabled:opacity-30"
              disabled={isPostTrack || i <= 0}
              title={t('prop_send_backward')}
              onClick={() => reorderClips(track.id, i, i - 1)}
            >
              <ChevronDown className="h-3.5 w-3.5" />
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}

function ClipPropertiesMenu({
  trackId,
  clip,
}: {
  trackId: string
  clip: Clip
}) {
  const t = useT()
  const locale = useProjectStore((s) => s.appSettings.locale)
  const catalogDetailCache = useProjectStore((s) => s.catalogDetailCache)
  const catalogClips = useProjectStore((s) => s.catalogClips)
  const ensureCatalogDetail = useProjectStore((s) => s.ensureCatalogDetail)
  const updateClip = useProjectStore((s) => s.updateClip)
  const appendEventLog = useProjectStore((s) => s.appendEventLog)
  const cacheKey = catalogDetailCacheKey(clip.clip_type, locale)
  const detail = catalogDetailCache[cacheKey]
  const [resetOpen, setResetOpen] = useState(false)

  const catalogEntry = catalogClips.find((n) => n.clip_type === clip.clip_type)
  const pluginId = detail?.plugin_id ?? catalogEntry?.plugin_id
  const clipLabel = catalogEntry?.label ?? humanizeClipType(clip.clip_type)
  const canExport = pluginId != null
  const canImport = detail != null && pluginId != null

  useEffect(() => {
    void ensureCatalogDetail(clip.clip_type)
  }, [clip.clip_type, ensureCatalogDetail])

  const importErrorMessage = (error: ImportClipParamsError): string => {
    switch (error.code) {
      case 'invalid_json':
        return t('prop_import_invalid_json')
      case 'invalid_format':
        return t('prop_import_invalid_format')
      case 'unsupported_format_version':
        return t('prop_import_unsupported_version').replace(
          '{version}',
          error.detail ?? '?',
        )
      case 'missing_params':
        return t('prop_import_missing_params')
      case 'plugin_id_mismatch':
        return t('prop_import_plugin_mismatch').replace('{type}', error.detail ?? '?')
      case 'clip_type_mismatch':
        return t('prop_import_clip_type_mismatch').replace('{type}', error.detail ?? '?')
      default:
        return t('prop_import_params_failed')
    }
  }

  const importSuccessMessage = (report: ImportClipParamsReport): string => {
    const parts = [t('prop_import_params_success')]
    if (report.defaultedFields.length > 0) {
      parts.push(
        t('prop_import_defaults_summary').replace('{fields}', report.defaultedFields.join(', ')),
      )
    }
    if (report.unknownFields.length > 0) {
      parts.push(
        t('prop_import_unknown_summary').replace('{fields}', report.unknownFields.join(', ')),
      )
    }
    if (report.structuralSkipped.length > 0) {
      parts.push(
        t('prop_import_structural_summary').replace(
          '{fields}',
          report.structuralSkipped.join(', '),
        ),
      )
    }
    return parts.join(' ')
  }

  const handleExport = () => {
    if (!pluginId) return
    void navigator.clipboard
      .writeText(
        serializeClipParamsExport(
          buildClipParamsExport({ clip, pluginId, clipLabel }),
        ),
      )
      .then(() => appendEventLog('info', t('prop_export_params_copied')))
      .catch(() => appendEventLog('error', t('prop_export_params_failed')))
  }

  const handleImport = () => {
    if (!detail || !pluginId) return
    void navigator.clipboard
      .readText()
      .then((text) => {
        const parsed = parseClipParamsClipboard(text)
        if (!parsed.ok) {
          appendEventLog('error', importErrorMessage(parsed.error))
          return
        }
        const identityError = validateClipParamsIdentity(parsed.payload, {
          pluginId,
          clipType: clip.clip_type,
        })
        if (identityError) {
          appendEventLog('error', importErrorMessage(identityError))
          return
        }
        const report = mergeImportedClipParams(detail, parsed.payload.params)
        updateClip(trackId, clip.id, { params: report.params })
        schedulePreviewRefresh()
        appendEventLog('info', importSuccessMessage(report))
      })
      .catch(() => appendEventLog('error', t('prop_import_clipboard_read_failed')))
  }

  const handleResetConfirm = () => {
    if (!detail) return
    updateClip(trackId, clip.id, { params: { ...detail.defaults } })
  }

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger
          className="h-6 w-6 shrink-0 grid place-items-center rounded text-muted-foreground hover:text-foreground hover:bg-accent"
          aria-label={t('prop_clip_menu')}
        >
          <MoreHorizontal className="h-3.5 w-3.5" />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" side="bottom" sideOffset={4} className="w-44">
          <DropdownMenuItem disabled={!canExport} onClick={handleExport}>
            {t('prop_export_params')}
          </DropdownMenuItem>
          <DropdownMenuItem disabled={!canImport} onClick={handleImport}>
            {t('prop_import_params')}
          </DropdownMenuItem>
          <DropdownMenuItem disabled={!detail} onClick={() => setResetOpen(true)}>
            {t('prop_reset_defaults')}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <AlertDialog open={resetOpen} onOpenChange={setResetOpen}>
        <AlertDialogContent size="sm">
          <AlertDialogHeader>
            <AlertDialogTitle>{t('prop_reset_defaults')}</AlertDialogTitle>
            <AlertDialogDescription>{t('prop_reset_defaults_confirm')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('dialog_cancel')}</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={handleResetConfirm}>
              {t('dialog_reset')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}

function ClipPresetDropdown({
  trackId,
  clipId,
  presets,
  presetLabels,
}: {
  trackId: string
  clipId: string
  presets: Array<{ id: string; values: Record<string, unknown> }>
  presetLabels: Record<string, string>
}) {
  const t = useT()
  const applyClipPreset = useProjectStore((s) => s.applyClipPreset)
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-muted-foreground">{t('prop_preset')}</span>
      <select
        className="w-full rounded border border-border bg-background px-2 py-1 text-xs outline-none focus:border-primary/60"
        value=""
        onChange={(e) => {
          const preset = presets.find((p) => p.id === e.target.value)
          if (preset) applyClipPreset(trackId, clipId, preset.values)
          e.target.value = ''
        }}
      >
        <option value="" disabled>{t('prop_preset_placeholder')}</option>
        {presets.map((p) => (
          <option key={p.id} value={p.id}>
            {presetLabels[p.id] ?? p.id}
          </option>
        ))}
      </select>
    </div>
  )
}

function ClipParamsEditor({
  trackId,
  clip,
}: {
  trackId: string
  clip: Clip
}) {
  const locale = useProjectStore((s) => s.appSettings.locale)
  const catalogDetailCache = useProjectStore((s) => s.catalogDetailCache)
  const ensureCatalogDetail = useProjectStore((s) => s.ensureCatalogDetail)
  const cacheKey = catalogDetailCacheKey(clip.clip_type, locale)
  const detail = catalogDetailCache[cacheKey]
  const [, setLoadTick] = useState(0)

  useEffect(() => {
    let active = true
    void ensureCatalogDetail(clip.clip_type).then(() => {
      if (active) setLoadTick((n) => n + 1)
    })
    return () => {
      active = false
    }
  }, [clip.clip_type, locale, ensureCatalogDetail])

  const rawPresets = detail?.ui?.presets
  const presets = Array.isArray(rawPresets)
    ? (rawPresets as Array<{ id: string; values: Record<string, unknown> }>)
    : []
  const presetLabels = (detail?.labels as ClipCatalogLabels | undefined)?.presets ?? {}

  const customUi = detail?.ui?.custom_ui
  if (customUi != null && customUi !== undefined) {
    return (
      <div className="flex flex-col gap-2 mt-1">
        <p className="text-[10px] text-muted-foreground">
          This clip uses a custom properties UI (not supported in the web editor yet).
        </p>
        <ParamsView params={clip.params} />
      </div>
    )
  }

  if (!detail) {
    return <ParamsView params={clip.params} />
  }

  return (
    <div className="flex flex-col gap-2">
      {presets.length > 0 && (
        <ClipPresetDropdown
          trackId={trackId}
          clipId={clip.id}
          presets={presets}
          presetLabels={presetLabels}
        />
      )}
      {clip.clip_type === 'std-video' && typeof clip.params.source === 'string' ? (
        <>
          <VideoOptimizedBanner source={clip.params.source} />
          <VideoFitDuration
            trackId={trackId}
            clip={clip}
            source={clip.params.source}
            startOffset={clip.params.start_offset}
            playbackRate={clip.params.playback_rate}
          />
        </>
      ) : null}
      {clip.clip_type === BACKGROUND_IMAGE_CLIP_TYPE &&
      typeof clip.params.source === 'string' &&
      clip.params.source.trim() ? (
        <BackgroundImageExtractTheme source={clip.params.source} />
      ) : null}
      <DynamicClipForm
        detail={detail}
        params={clip.params}
        trackId={trackId}
        clipId={clip.id}
      />
    </div>
  )
}

function ProjectSettingParamsEditor({ setting }: { setting: ProjectSetting }) {
  const locale = useProjectStore((s) => s.appSettings.locale)
  const catalogDetailCache = useProjectStore((s) => s.catalogDetailCache)
  const ensureCatalogDetail = useProjectStore((s) => s.ensureCatalogDetail)
  const cacheKey = catalogDetailCacheKey(setting.clip_type, locale)
  const detail = catalogDetailCache[cacheKey]
  const [, setLoadTick] = useState(0)

  useEffect(() => {
    let active = true
    void ensureCatalogDetail(setting.clip_type).then(() => {
      if (active) setLoadTick((n) => n + 1)
    })
    return () => {
      active = false
    }
  }, [setting.clip_type, locale, ensureCatalogDetail])

  const customUi = detail?.ui?.custom_ui
  if (customUi != null && customUi !== undefined) {
    return <ParamsView params={setting.params} />
  }

  if (!detail) {
    return <ParamsView params={setting.params} />
  }

  return (
    <DynamicClipForm
      detail={detail}
      params={setting.params}
      projectSettingId={setting.id}
    />
  )
}

function ClipUnavailableBanner({ clipType }: { clipType: string }) {
  const t = useT()
  const broken = useIsClipBroken(clipType)
  if (!broken) return null
  return <p className="text-xs text-destructive">{t('prop_plugin_missing')}</p>
}

function Field({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-muted-foreground">{label}</span>
      <span className={mono ? 'font-mono text-foreground break-all' : 'text-foreground'}>
        {value}
      </span>
    </div>
  )
}

function ParamsView({ params }: { params: Record<string, unknown> }) {
  const t = useT()
  const entries = Object.entries(params)
  if (entries.length === 0) return null
  return (
    <div className="flex flex-col gap-1 mt-1">
      <span className="text-muted-foreground uppercase text-[10px] tracking-wider">{t('prop_params')}</span>
      {entries.map(([k, v]) => (
        <div key={k} className="flex justify-between gap-2">
          <span className="text-muted-foreground">{k}</span>
          <span className="font-mono text-foreground truncate">{String(v)}</span>
        </div>
      ))}
    </div>
  )
}
