import { useState } from 'react'
import { ArrowLeftRight, Music2, Settings2 } from 'lucide-react'
import { TypographyPanel } from '@/components/typography/TypographyPanel'
import { ThemePanel } from '@/components/theme/ThemePanel'
import { useSoundIsAnalyzing } from '@/hooks/useAudioAnalysisCoordinator'
import { useProjectStore, type ExportQuality } from '@/store/projectStore'
import { duplicateBusNames } from '@/lib/audioBuses'
import { useMemo } from 'react'
import {
  PLATFORM_GROUP_LABEL_KEYS,
  PLATFORM_GROUP_ORDER,
  type PlatformPresetId,
} from '@/lib/platformPresets'
import { filterPlatformPresets, resolutionFitsRenderLimits } from '@/lib/renderLimits'
import { useT } from '@/lib/i18n'
import type { TranslationKey } from '@/lib/i18n'
import type { Sound } from '@/lib/sound'
import { ComposeLauncher } from '@/components/layout/ComposeLauncher'

// ---- FPS options ----------------------------------------------------------

const EXPORT_QUALITY_OPTIONS: { value: ExportQuality; labelKey: TranslationKey; hintKey: TranslationKey }[] = [
  { value: 'draft', labelKey: 'export_quality_draft', hintKey: 'export_quality_draft_hint' },
  { value: 'standard', labelKey: 'export_quality_standard', hintKey: 'export_quality_standard_hint' },
  { value: 'master', labelKey: 'export_quality_master', hintKey: 'export_quality_master_hint' },
]

const FPS_OPTIONS: { value: number; hintKey: TranslationKey }[] = [
  { value: 12, hintKey: 'fps_12_hint' },
  { value: 15, hintKey: 'fps_15_hint' },
  { value: 20, hintKey: 'fps_20_hint' },
  { value: 24, hintKey: 'fps_24_hint' },
  { value: 25, hintKey: 'fps_25_hint' },
  { value: 30, hintKey: 'fps_30_hint' },
]

// ---- Resolution presets ---------------------------------------------------

interface ResolutionPreset {
  label: string
  width: number
  height: number
  hintKey?: TranslationKey
}

const VERTICAL_PRESETS: ResolutionPreset[] = [
  { label: '1080 × 1920', width: 1080, height: 1920 },
  { label: '720 × 1280',  width: 720,  height: 1280 },
  { label: '540 × 960',   width: 540,  height: 960  },
  { label: '480 × 854',   width: 480,  height: 854  },
  { label: '360 × 640',   width: 360,  height: 640  },
  { label: '270 × 480',   width: 270,  height: 480  },
  { label: '180 × 320',   width: 180,  height: 320  },
]

const OTHER_PRESETS: ResolutionPreset[] = [
  { label: '960 × 540', width: 960, height: 540 },
  { label: '1080 × 1350', width: 1080, height: 1350, hintKey: 'res_hint_45' },
  { label: '1080 × 1080', width: 1080, height: 1080, hintKey: 'res_hint_11' },
  { label: '720 × 720',   width: 720,  height: 720,  hintKey: 'res_hint_11' },
]

// ---- Duration presets -----------------------------------------------------

const DURATION_PRESETS: { value: number; hintKey: TranslationKey }[] = [
  { value: 5,  hintKey: 'dur_5_hint'  },
  { value: 8,  hintKey: 'dur_8_hint'  },
  { value: 10, hintKey: 'dur_10_hint' },
  { value: 15, hintKey: 'dur_15_hint' },
  { value: 20, hintKey: 'dur_20_hint' },
  { value: 30, hintKey: 'dur_30_hint' },
  { value: 45, hintKey: 'dur_45_hint' },
  { value: 60, hintKey: 'dur_60_hint' },
]

// ---- Helpers --------------------------------------------------------------

function presetKey(w: number, h: number) { return `${w}x${h}` }

function matchResolutionPreset(w: number, h: number, presets: ResolutionPreset[]): string {
  const match = presets.find((p) => p.width === w && p.height === h)
  return match ? presetKey(match.width, match.height) : 'custom'
}

function formatResolutionLabel(w: number, h: number): string {
  return `${w} × ${h}`
}


function AudioBusListItem({ sound, isDupe }: { sound: Sound; isDupe: boolean }) {
  const t = useT()
  const isAnalyzing = useSoundIsAnalyzing(sound.id)
  const name = sound.bus.trim() || t('sound_untitled')

  return (
    <div
      className={`flex items-center gap-2 rounded border px-2 py-1.5 ${
        isDupe ? 'border-amber-500/40 bg-amber-500/10' : 'border-border/60 bg-muted/30'
      }`}
    >
      <span className="text-[9px] font-semibold px-1 rounded bg-green-500/20 text-green-400 leading-4 shrink-0">
        Audio
      </span>
      <span className="truncate text-foreground">
        {name}
        {isAnalyzing ? (
          <span className="ml-1 text-[10px] text-muted-foreground">{t('sound_analyzing')}</span>
        ) : null}
      </span>
    </div>
  )
}

// ---- Component ------------------------------------------------------------

export function LeftPanel() {
  const t = useT()
  const meta = useProjectStore((s) => s.meta)
  const setMeta = useProjectStore((s) => s.setMeta)
  const serverConfig = useProjectStore((s) => s.serverConfig)
  const platformPresetId = useProjectStore((s) => s.platformPresetId)
  const setPlatformPresetId = useProjectStore((s) => s.setPlatformPresetId)
  const applyPlatformPreset = useProjectStore((s) => s.applyPlatformPreset)
  const sounds = useProjectStore((s) => s.sounds)
  const isPlaying = useProjectStore((s) => s.isPlaying)

  const availablePlatformPresets = useMemo(
    () => filterPlatformPresets(serverConfig),
    [serverConfig],
  )
  const availableDurationPresets = useMemo(
    () => DURATION_PRESETS.filter((p) => p.value <= serverConfig.maxDurationS),
    [serverConfig.maxDurationS],
  )
  const availableFpsOptions = useMemo(
    () => FPS_OPTIONS.filter((f) => f.value <= serverConfig.maxFps),
    [serverConfig.maxFps],
  )
  const availableVerticalPresets = useMemo(
    () => VERTICAL_PRESETS.filter((p) => resolutionFitsRenderLimits(p.width, p.height, serverConfig)),
    [serverConfig],
  )
  const availableOtherPresets = useMemo(
    () => OTHER_PRESETS.filter((p) => resolutionFitsRenderLimits(p.width, p.height, serverConfig)),
    [serverConfig],
  )
  const availableResolutionPresets = useMemo(
    () => [...availableVerticalPresets, ...availableOtherPresets],
    [availableVerticalPresets, availableOtherPresets],
  )

  /** User picked "Custom" while still on a preset value; cleared when a preset is chosen. */
  const [durationCustomMode, setDurationCustomMode] = useState(
    () => !DURATION_PRESETS.some((p) => p.value === meta.duration),
  )
  const durationPreset = availableDurationPresets.find((p) => p.value === meta.duration)
  const showCustomDuration = durationCustomMode || durationPreset === undefined

  const [resolutionCustomMode, setResolutionCustomMode] = useState(false)

  const duplicateBuses = duplicateBusNames(sounds)
  const matchedResolutionKey = matchResolutionPreset(meta.width, meta.height, availableResolutionPresets)
  const isCustomResolution = matchedResolutionKey === 'custom'
  const resolutionSelectValue = isCustomResolution ? 'custom' : matchedResolutionKey
  const canSwapResolution = meta.width !== meta.height
  const currentResolutionHintKey = availableResolutionPresets.find(
    (p) => p.width === meta.width && p.height === meta.height
  )?.hintKey

  const currentFpsHintKey = availableFpsOptions.find((f) => f.value === meta.fps)?.hintKey
  const currentExportQuality = EXPORT_QUALITY_OPTIONS.find((q) => q.value === meta.exportQuality)
    ?? EXPORT_QUALITY_OPTIONS[2]

  const activePlatform = platformPresetId
    ? availablePlatformPresets.find((p) => p.id === platformPresetId)
    : undefined
  const durationOverPlatformMax =
    activePlatform !== undefined && meta.duration > activePlatform.maxSec

  return (
    <div data-transport-block className="flex flex-col h-full text-xs overflow-y-auto">

      {/* ── Project Settings ── */}
      <section className="flex flex-col border-b border-border">
        <div className="flex items-center gap-1.5 px-3 py-2 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider select-none">
          <Settings2 className="w-3 h-3" />
          {t('left_project')}
        </div>
        <fieldset disabled={isPlaying} className={`contents ${isPlaying ? 'opacity-40' : ''}`}>
        <div className="flex flex-col gap-2 px-3 pb-3">


          {/* Title */}
          <label className="flex items-center justify-between gap-2">
            <span className="text-muted-foreground shrink-0">{t('left_title')}</span>
            <input
              type="text"
              className="rounded border border-border bg-muted/50 px-1.5 py-0.5 text-xs text-foreground outline-none focus:border-primary/60 w-28 text-right"
              value={meta.title}
              onChange={(e) => setMeta({ title: e.target.value })}
              placeholder={t('left_title_default')}
            />
          </label>

          {/* Author */}
          <label className="flex items-center justify-between gap-2">
            <span className="text-muted-foreground shrink-0">{t('left_author')}</span>
            <input
              type="text"
              className="rounded border border-border bg-muted/50 px-1.5 py-0.5 text-xs text-foreground outline-none focus:border-primary/60 w-28 text-right"
              value={meta.author}
              onChange={(e) => setMeta({ author: e.target.value })}
              placeholder={t('left_author_placeholder')}
            />
          </label>

          {/* Platform */}
          <div className="flex flex-col gap-0.5">
            <label className="flex items-center justify-between gap-2">
              <span className="text-muted-foreground shrink-0">{t('left_platform')}</span>
              <select
                className="rounded border border-border bg-muted/50 px-1.5 py-0.5 text-xs text-foreground outline-none focus:border-primary/60 w-28"
                value={platformPresetId ?? 'custom'}
                onChange={(e) => {
                  const val = e.target.value
                  if (val === 'custom') {
                    setPlatformPresetId(null)
                    return
                  }
                  applyPlatformPreset(val as PlatformPresetId)
                }}
              >
                {PLATFORM_GROUP_ORDER.map((group) => {
                  const groupPresets = availablePlatformPresets.filter((p) => p.group === group)
                  if (groupPresets.length === 0) return null
                  return (
                  <optgroup key={group} label={t(PLATFORM_GROUP_LABEL_KEYS[group])}>
                    {groupPresets.map((p) => (
                      <option key={p.id} value={p.id}>
                        {t(p.labelKey)}
                      </option>
                    ))}
                  </optgroup>
                  )
                })}
                <option value="custom">{t('left_platform_custom')}</option>
              </select>
            </label>
          </div>

          {/* Resolution */}
          <div className="flex flex-col gap-0.5">
            <label className="flex items-center justify-between gap-2">
              <span className="text-muted-foreground shrink-0">{t('left_resolution')}</span>
              <div className="flex items-center gap-0.5">
                <select
                  className="rounded border border-border bg-muted/50 px-1.5 py-0.5 text-xs text-foreground outline-none focus:border-primary/60 w-24"
                  value={resolutionSelectValue}
                  onChange={(e) => {
                    const val = e.target.value
                    if (val === 'custom') return
                    if (val === 'custom-edit') {
                      setResolutionCustomMode(true)
                      return
                    }
                    setResolutionCustomMode(false)
                    const preset = availableResolutionPresets.find((p) => presetKey(p.width, p.height) === val)
                    if (preset) setMeta({ width: preset.width, height: preset.height })
                  }}
                >
                  <optgroup label={t('optgroup_vertical')}>
                    {availableVerticalPresets.map((p) => (
                      <option key={presetKey(p.width, p.height)} value={presetKey(p.width, p.height)}>
                        {p.label}{p.hintKey ? `  ${t(p.hintKey)}` : ''}
                      </option>
                    ))}
                  </optgroup>
                  <optgroup label={t('optgroup_other')}>
                    {availableOtherPresets.map((p) => (
                      <option key={presetKey(p.width, p.height)} value={presetKey(p.width, p.height)}>
                        {p.label}{p.hintKey ? `  ${t(p.hintKey)}` : ''}
                      </option>
                    ))}
                  </optgroup>
                  {isCustomResolution && (
                    <option value="custom">
                      {formatResolutionLabel(meta.width, meta.height)}
                    </option>
                  )}
                  <option value="custom-edit">{t('left_resolution_custom')}</option>
                </select>
                <button
                  type="button"
                  disabled={!canSwapResolution}
                  title={t('left_resolution_swap')}
                  aria-label={t('left_resolution_swap')}
                  className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded border border-border bg-muted/50 text-muted-foreground outline-none hover:text-foreground hover:border-primary/60 focus:border-primary/60 disabled:opacity-40 disabled:pointer-events-none"
                  onClick={() => {
                    if (!canSwapResolution) return
                    setResolutionCustomMode(false)
                    setMeta({ width: meta.height, height: meta.width })
                  }}
                >
                  <ArrowLeftRight className="w-3 h-3" />
                </button>
              </div>
            </label>
            {currentResolutionHintKey && (
              <p className="text-[10px] text-muted-foreground text-right pr-0.5">{t(currentResolutionHintKey)}</p>
            )}
            {resolutionCustomMode && (
              <div className="flex flex-col gap-1 mt-0.5">
                <label className="flex items-center justify-between gap-2">
                  <span className="text-muted-foreground shrink-0 pl-2">{t('left_resolution_width')}</span>
                  <input
                    type="number" min={1} max={serverConfig.maxWidth} step={1}
                    className="rounded border border-border bg-muted/50 px-1.5 py-0.5 text-xs text-foreground outline-none focus:border-primary/60 w-20 text-right"
                    value={meta.width}
                    onChange={(e) => {
                      const v = Number(e.target.value)
                      if (v > 0) setMeta({ width: Math.min(v, serverConfig.maxWidth) })
                    }}
                  />
                </label>
                <label className="flex items-center justify-between gap-2">
                  <span className="text-muted-foreground shrink-0 pl-2">{t('left_resolution_height')}</span>
                  <input
                    type="number" min={1} max={serverConfig.maxHeight} step={1}
                    className="rounded border border-border bg-muted/50 px-1.5 py-0.5 text-xs text-foreground outline-none focus:border-primary/60 w-20 text-right"
                    value={meta.height}
                    onChange={(e) => {
                      const v = Number(e.target.value)
                      if (v > 0) setMeta({ height: Math.min(v, serverConfig.maxHeight) })
                    }}
                  />
                </label>
              </div>
            )}
          </div>

        {/* Duration */}
          <div className="flex flex-col gap-0.5">
            <label className="flex items-center justify-between gap-2">
              <span className="text-muted-foreground shrink-0">{t('left_duration')}</span>
              <select
                className="rounded border border-border bg-muted/50 px-1.5 py-0.5 text-xs text-foreground outline-none focus:border-primary/60 w-28"
                value={showCustomDuration ? 'custom' : String(meta.duration)}
                onChange={(e) => {
                  if (e.target.value === 'custom') {
                    setDurationCustomMode(true)
                  } else {
                    setDurationCustomMode(false)
                    setMeta({ duration: Number(e.target.value) })
                  }
                }}
              >
                {availableDurationPresets.map((p) => (
                  <option key={p.value} value={String(p.value)}>
                    {p.value}s — {t(p.hintKey)}
                  </option>
                ))}
                <option value="custom">{t('left_duration_custom')}</option>
              </select>
            </label>
            {!showCustomDuration && durationPreset ? (
              <p className="text-[10px] text-muted-foreground text-right pr-0.5">
                {t(durationPreset.hintKey)}
              </p>
            ) : null}
            {durationOverPlatformMax && activePlatform ? (
              <p className="text-[10px] text-amber-500/90 text-right pr-0.5">
                {t('platform_duration_over_max')
                  .replace('{platform}', t(activePlatform.labelKey))
                  .replace('{max}', String(activePlatform.maxSec))}
              </p>
            ) : null}
            {showCustomDuration ? (
              <label className="flex items-center justify-between gap-2">
                <span className="text-muted-foreground shrink-0 pl-2">{t('left_duration_seconds')}</span>
                <div className="flex items-center gap-1">
                  <input
                    type="number"
                    min={1 / meta.fps}
                    max={serverConfig.maxDurationS}
                    step={1 / meta.fps}
                    className="rounded border border-border bg-muted/50 px-1.5 py-0.5 text-xs text-foreground outline-none focus:border-primary/60 w-16 text-right"
                    value={meta.duration}
                    onChange={(e) => {
                      const v = Number(e.target.value)
                      if (v > 0) {
                        setMeta({ duration: Math.min(v, serverConfig.maxDurationS) })
                      }
                    }}
                  />
                  <span className="text-muted-foreground">s</span>
                </div>
              </label>
            ) : null}
          </div>

          {/* FPS */}
          <div className="flex flex-col gap-0.5">
            <label className="flex items-center justify-between gap-2">
              <span className="text-muted-foreground shrink-0">{t('left_fps')}</span>
              <select
                className="rounded border border-border bg-muted/50 px-1.5 py-0.5 text-xs text-foreground outline-none focus:border-primary/60 w-28"
                value={meta.fps}
                onChange={(e) => setMeta({ fps: Number(e.target.value) })}
              >
                {availableFpsOptions.map((f) => (
                  <option key={f.value} value={f.value}>
                    {f.value} — {t(f.hintKey)}
                  </option>
                ))}
              </select>
            </label>
            {currentFpsHintKey && (
              <p className="text-[10px] text-muted-foreground text-right pr-0.5">{t(currentFpsHintKey)}</p>
            )}
          </div>

          {/* Export quality */}
          <div className="flex flex-col gap-0.5">
            <label className="flex items-center justify-between gap-2">
              <span className="text-muted-foreground shrink-0">{t('left_export_quality')}</span>
              <select
                className="rounded border border-border bg-muted/50 px-1.5 py-0.5 text-xs text-foreground outline-none focus:border-primary/60 w-36"
                value={meta.exportQuality}
                onChange={(e) =>
                  setMeta({ exportQuality: e.target.value as ExportQuality })
                }
              >
                {EXPORT_QUALITY_OPTIONS.map((q) => (
                  <option key={q.value} value={q.value}>
                    {t(q.labelKey)}
                  </option>
                ))}
              </select>
            </label>
            <p className="text-[10px] text-muted-foreground text-right pr-0.5">
              {t(currentExportQuality.hintKey)}
            </p>
          </div>

        </div>
        </fieldset>
      </section>

      {/* ── Audio Buses ── */}
      <section className="flex flex-col border-b border-border shrink-0">
        <div className="flex items-center gap-1.5 px-3 py-2 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider select-none">
          <Music2 className="w-3 h-3" />
          {t('left_audio_buses')}
        </div>
        <div className="px-3 pb-3 flex flex-col gap-1.5">
          {sounds.length === 0 ? (
            <p className="text-muted-foreground italic leading-snug">
              {t('left_no_audio_tracks')}
              <br />
              {t('left_no_audio_tracks_hint')}
            </p>
          ) : (
            sounds.map((sound) => (
              <AudioBusListItem
                key={sound.id}
                sound={sound}
                isDupe={sound.bus.trim().length > 0 && duplicateBuses.has(sound.bus.trim())}
              />
            ))
          )}
        </div>
      </section>

      <ComposeLauncher />

      <TypographyPanel />

      <ThemePanel />

    </div>
  )
}
