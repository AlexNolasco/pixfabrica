import { create } from 'zustand'
import { isClipSelection } from '@/lib/selection'
import { PROJECT_UNDO_HISTORY_LIMIT } from '@/lib/clientLimits'
import { temporal } from 'zundo'
import { ApiHttpError, apiGet } from '@/lib/apiClient'
import messages from '@/lib/i18n.messages.json'
import { FALLBACK_FONT_CATALOG, fetchFontCatalog as fetchFontCatalogApi, type FontFamilyEntry } from '@/lib/fonts'
import {
  DEFAULT_FONT_PALETTE,
  applyGlobalFamilies,
  cloneFontPalette,
  monoFamilyFromPalette,
  sansFamilyFromPalette,
  type FontPalette,
  type FontRole,
} from '@/lib/typography'
import {
  DEFAULT_JOB_COLORS,
  DEFAULT_PALETTE_SOURCE,
  cloneJobColors,
  type JobColorPalette,
  type PaletteSource,
  type ThemeName,
  type ThemeVariant,
} from '@/lib/jobColors'
import { type ColorTokenName } from '@/lib/themeColor'
import { toRenderJob } from '@/lib/renderJob'
import {
  DEFAULT_PLATFORM_PRESET_ID,
  getPlatformPreset,
  type PlatformPresetId,
} from '@/lib/platformPresets'
import type { Sound } from '@/lib/sound'
import { sanitizeSoundPatch } from '@/lib/sound'
import { resetPrepareWarningDiagnostics } from '@/lib/prepareWarningDiagnostics'
import { clearAudioBufferCache } from '@/lib/audioBufferCache'
import { clearWaveformPeaksCache } from '@/lib/waveformPeaks'
import type { PrepareWarningItem } from '@/lib/prepareWarningTypes'
import {
  defaultTimelineLayout,
  removeFromLayout,
  resolveTimelineLayout,
  soundsOrderFromLayout,
  tracksOrderFromLayout,
  type TimelineLayoutEntry,
} from '@/lib/timelineLayout'
import { canAddClipToTrack } from '@/lib/projectLimits'
import { bandLayoutPatchForSecondClip } from '@/lib/trackVisualSettings'
import { fetchThemePresets, FALLBACK_THEME_PRESETS, type ThemePresetEntry } from '@/lib/themePresets'
import { normalizeClipPreviewMode, type ClipPreviewMode } from '@/lib/clipPreviewMode'
import {
  fallbackServerConfig,
  parseServerConfigPayload,
  type ServerConfig,
  type ServerConfigPayload,
} from '@/lib/serverConfig'
import { reconcileMetaWithRenderLimits } from '@/lib/renderLimits'
import type { ComposeHealth } from '@/lib/composeHealth'
import {
  catalogDetailCacheKey,
  normalizeCatalogEffect,
  paramsNeedDefaultsHydration,
  type ClipCatalogDetail,
} from '@/lib/catalogDetail'
import type { TimelineImportBatch } from '@/lib/timelineDrop/types'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ProjectMeta {
  title: string
  author: string
  fps: number
  duration: number // seconds
  width: number
  height: number
  /** Full-render encode quality preset (travels with the project). */
  exportQuality: ExportQuality
}

export interface Transition {
  type: 'fade' | 'slide' | 'scale' | 'blur' | 'wipe'
  duration: number
  easing: string
  direction?: 'left' | 'right' | 'up' | 'down'
}

/** Per-clip effect instance (inline on a visual clip). */
export interface EffectInstance {
  id: string
  effect_type: string
  label?: string
  enabled?: boolean
  params: Record<string, unknown>
}

/** A clip is a single plugin instance placed on a track. */
export interface Clip {
  id: string
  clip_type: string // e.g. "std-background-image"
  label: string
  start: number // seconds, relative to project start
  duration: number | null // null = inherit from track → project
  enabled: boolean
  params: Record<string, unknown>
  effects?: EffectInstance[]
  /** Only set in the store, never serialized. Present when the plugin is not installed. */
  status?: 'missing_plugin'
}

/** A track is a named layer that contains ordered clips. */
export interface Track {
  id: string
  label: string
  enabled: boolean
  disableMode: 'mute_output' | 'bypass_compute'
  start: number // seconds
  duration: number | null // null = inherit from project
  layout: 'fill' | 'vertical' | 'horizontal'
  /** First band size for vertical/horizontal two-clip tracks; null = equal split. */
  headerFraction?: number | null
  trackType?: 'skia' | 'gl' | 'audio' | 'post' // optional for backwards compat; defaults to 'skia'
  transition_in?: Transition
  transition_out?: Transition
  clips: Clip[]
  effects?: EffectInstance[]
}

/** Job-level settings that are not part of the timeline (Theme, Lyrics generator, etc.) */
export interface ProjectSetting {
  id: string
  clip_type: string
  label: string
  params: Record<string, unknown>
  status?: 'missing_plugin'
}

export interface LayoutPrefs {
  leftWidthPct: number
  rightWidthPct: number
  previewHeightPct: number
  leftCollapsed: boolean
  rightCollapsed: boolean
}

export type ThemeMode = 'dark' | 'light' | 'system'
export type UiLocale = 'en' | 'es' | 'zh-CN' | 'ja'

export type ThumbnailExportResolution = 'full' | 'preview'

export type ExportQuality = 'draft' | 'standard' | 'master'

export type VideoEncoder = 'auto' | 'cpu' | 'nvenc'

export interface AppSettings {
  /** UI locale; full i18n wiring comes later. */
  locale: UiLocale
  /** Debounce (ms) before refreshing preview after edits. */
  previewDebounceMs: number
  /** Default loop length (seconds) for isolated clip mini-preview Play. */
  previewClipLoopSeconds: number
  /** Global preview mode while a clip is selected (resets on project load). */
  clipPreviewMode: ClipPreviewMode
  /** Composition frame download: full project resolution vs on-screen preview only. */
  thumbnailExportResolution: ThumbnailExportResolution
  /** Render strategy for submitted jobs. */
  renderParallelism: 'single' | 'multi'
  /** FFmpeg video encoder for full renders. */
  videoEncoder: VideoEncoder
}

export type ApiConnectionStatus = 'checking' | 'connected' | 'disconnected'

export type AppView = 'editor' | 'jobs'

export type CatalogTrackKind = 'skia' | 'gl' | 'post'

export type EffectBackend = 'gl' | 'skia' | 'raster'

export interface CatalogEffectItem {
  effect_type: string
  label: string
  description: string
  icon: string
  effect_backend: EffectBackend
  category: string
  tags: string[]
  plugin_id: string
  disabled: boolean
  pinned: boolean
  license: string
  restricted_reason?: string | null
}

export interface CatalogClipItem {
  clip_type: string
  label: string
  description: string
  icon: string
  track_kind: CatalogTrackKind
  category: string
  tags: string[]
  plugin_id: string
  disabled: boolean
  pinned: boolean
  license: string
  restricted_reason?: string | null
}

export type CatalogLoadStatus = 'idle' | 'loading' | 'ready' | 'error'

export interface PluginPickerState {
  trackId: string
  trackKind?: CatalogTrackKind
  mode?: 'clip' | 'effect'
  effectScope?: 'clip' | 'track'
  clipId?: string
  effectBackend?: EffectBackend
}

/** Ephemeral UI feedback after adding from the plugin catalog (not undo history). */
export interface CatalogAddFeedback {
  trackId: string
  clipId: string
  clipType: string
}

export interface EventLogEntry {
  id: string
  at: number
  level: 'info' | 'warn' | 'error'
  message: string
}

export interface ComposeChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
}

// ---------------------------------------------------------------------------
// Store shape
// ---------------------------------------------------------------------------

export interface ProjectState {
  meta: ProjectMeta
  typography: FontPalette
  colors: JobColorPalette
  paletteSource: PaletteSource
  projectSettings: ProjectSetting[]
  tracks: Track[]
  sounds: Sound[]
  /** Editor-only row order (top → bottom). Not exported in RenderJob. */
  timelineLayout: TimelineLayoutEntry[]
  /** Host-local folder id under media/bundles/ after bundle import (not shared). */
  importBundleId: string | null

  /** Currently selected entity for the properties panel. */
  selection:
    | { kind: 'clip'; trackId: string; clipId: string }
    | { kind: 'track'; trackId: string }
    | { kind: 'sound'; soundId: string }
    | { kind: 'projectSetting'; projectSettingId: string }
    | null

  /** Right-panel plugin catalog (replaces Properties while set). */
  pluginPicker: PluginPickerState | null
  /** Right-panel compose chat (replaces Properties while open). */
  composePanelOpen: boolean
  composeSessionId: string | null
  composeMessages: ComposeChatMessage[]
  composeLastProject: Record<string, unknown> | null
  catalogClips: CatalogClipItem[]
  catalogEffects: CatalogEffectItem[]
  catalogLoadStatus: CatalogLoadStatus
  catalogSearchByKind: Record<CatalogTrackKind, string>
  catalogAddFeedback: CatalogAddFeedback | null
  /** Merged UI spec + schema keyed by `${clipType}:${locale}` (not in graph JSON). */
  catalogDetailCache: Record<string, ClipCatalogDetail>

  fontCatalog: FontFamilyEntry[]
  fontCatalogFallback: boolean

  themePresets: ThemePresetEntry[]
  themePresetsFallback: boolean

  serverConfig: ServerConfig
  serverConfigWarned: boolean

  themeMode: ThemeMode
  appLayoutPrefs: LayoutPrefs
  appFavoriteClipTypes: string[]
  apiConnectionStatus: ApiConnectionStatus
  apiRetryInSeconds: number | null
  apiRetryNonce: number
  /** From GET /health compose block; null until first successful health check. */
  composeHealth: ComposeHealth | null
  /** From GET /health; null until first successful health check. */
  pexelsAvailable: boolean | null
  /** From GET /health; null until first successful health check. */
  ffmpegAvailable: boolean | null
  showLogsPanel: boolean
  showSettingsPanel: boolean
  appView: AppView
  focusedJobId: string | null
  appSettings: AppSettings
  eventLogs: EventLogEntry[]
  /** Bumps on loadProject/resetProject so timeline UI can react (e.g. expand all tracks). */
  projectLoadEpoch: number

  /** Ephemeral — last preview prepare reported missing/unreachable sources. */
  prepareWarnings: PrepareWarningItem[]
  setPrepareWarnings: (items: PrepareWarningItem[]) => void
  isPlaying: boolean
  setIsPlaying: (playing: boolean) => void
  /** Playhead time (seconds) shared with preview pane. */
  previewTime: number
  setPreviewTime: (t: number) => void
  /** Session-only — mutes timeline + clip preview audio, not render. */
  previewMuted: boolean
  setPreviewMuted: (muted: boolean) => void
  togglePreviewMuted: () => void

  /** Session-only export target label; not serialized with the project. */
  platformPresetId: PlatformPresetId | null
  setPlatformPresetId: (id: PlatformPresetId | null) => void
  applyPlatformPreset: (id: PlatformPresetId) => void

  // ---- Meta actions -------------------------------------------------------
  setMeta: (patch: Partial<ProjectMeta>) => void

  setSansFamily: (family: string) => void
  setMonoFamily: (family: string) => void
  setRoleTypography: (role: FontRole, patch: { weight?: number; size?: number }) => void
  fetchFontCatalog: () => Promise<void>

  fetchThemePresets: () => Promise<void>
  fetchServerConfig: () => Promise<void>
  applyNamedPreset: (
    theme: ThemeName,
    variant: ThemeVariant,
    colors: JobColorPalette,
  ) => void
  applyExtractedPalette: (colors: JobColorPalette, filename: string) => void
  applyCustomPalette: (colors: JobColorPalette) => void
  setJobColor: (token: ColorTokenName, hex: string) => void

  // ---- Track actions ------------------------------------------------------
  addTrack: (track: Track) => void
  updateTrack: (trackId: string, patch: Partial<Omit<Track, 'id' | 'clips'>>) => void
  removeTrack: (trackId: string) => void
  duplicateTrack: (trackId: string) => void
  toggleTrackEnabled: (trackId: string) => void
  reorderTracks: (fromIndex: number, toIndex: number) => void

  // ---- Sound actions ------------------------------------------------------
  addSound: (sound: Sound) => void
  updateSound: (soundId: string, patch: Partial<Omit<Sound, 'id'>>) => void
  /** One undo step: set job duration and reset this sound span (start 0, inherit duration). */
  applyFitProjectToSound: (soundId: string, newDuration: number) => void
  removeSound: (soundId: string) => void
  duplicateSound: (soundId: string) => void
  toggleSoundEnabled: (soundId: string) => void

  reorderTimelineLayout: (fromIndex: number, toIndex: number) => void

  // ---- Clip actions ----------------------------------------------------
  addClip: (trackId: string, clip: Clip) => void
  /** Add or replace (post track) from catalog; keeps picker open, sets flash feedback. */
  addCatalogClip: (trackId: string, clipType: string, label: string) => void
  /** One undo step: timeline file drop (images and/or audio). */
  applyTimelineImportBatch: (batch: TimelineImportBatch) => {
    frontTrackId?: string
    frontClipId?: string
    frontSoundId?: string
  } | null
  hydrateClipDefaults: (
    trackId: string,
    clipId: string,
    clipType: string,
  ) => Promise<boolean>
  /** Load catalog detail (ui + labels) into cache for the current locale. */
  ensureCatalogDetail: (
    clipType: string,
    kind?: 'clip' | 'effect',
  ) => Promise<ClipCatalogDetail | null>
  updateClip: (trackId: string, clipId: string, patch: Partial<Omit<Clip, 'id'>>) => void
  toggleClipEnabled: (trackId: string, clipId: string) => void
  applyClipPreset: (trackId: string, clipId: string, values: Record<string, unknown>) => void
  removeClip: (trackId: string, clipId: string) => void
  /** Clone clip on the same track (inserted above source in z-order). */
  duplicateClip: (trackId: string, clipId: string) => void
  /** Clone clip after source when the track has room; applies optional patch. */
  insertClipCloneAfter: (
    trackId: string,
    afterClipId: string,
    patch?: Partial<Omit<Clip, 'id'>>,
  ) => string | null
  /** Move clip to another compatible track (front-most slot; post tracks replace). */
  moveClip: (fromTrackId: string, toTrackId: string, clipId: string) => void
  reorderClips: (trackId: string, fromIndex: number, toIndex: number) => void
  swapTrackClips: (trackId: string) => void

  // ---- Project setting actions ---------------------------------------------------
  addProjectSetting: (setting: ProjectSetting) => void
  updateProjectSetting: (projectSettingId: string, patch: Partial<Omit<ProjectSetting, 'id'>>) => void
  removeProjectSetting: (projectSettingId: string) => void

  // ---- Selection ----------------------------------------------------------
  select: (selection: ProjectState['selection']) => void
  clearSelection: () => void

  // ---- Plugin catalog -----------------------------------------------------
  openPluginPicker: (trackId: string, trackKind: CatalogTrackKind) => void
  openEffectPicker: (
    trackId: string,
    clipId: string,
    effectBackend?: EffectBackend,
  ) => void
  openTrackEffectPicker: (trackId: string, effectBackend?: EffectBackend) => void
  closePluginPicker: () => void
  openComposePanel: () => void
  closeComposePanel: () => void
  setComposeSessionId: (sessionId: string | null) => void
  appendComposeMessages: (messages: ComposeChatMessage[]) => void
  setComposeLastProject: (project: Record<string, unknown> | null) => void
  clearComposeChat: () => void
  addCatalogEffect: (trackId: string, clipId: string, effectType: string, label: string) => void
  addCatalogTrackEffect: (trackId: string, effectType: string, label: string) => void
  removeEffect: (trackId: string, clipId: string, effectId: string) => void
  removeTrackEffect: (trackId: string, effectId: string) => void
  reorderEffects: (
    trackId: string,
    clipId: string,
    fromIndex: number,
    toIndex: number,
  ) => void
  reorderTrackEffects: (trackId: string, fromIndex: number, toIndex: number) => void
  toggleEffectEnabled: (trackId: string, clipId: string, effectId: string) => void
  toggleTrackEffectEnabled: (trackId: string, effectId: string) => void
  updateEffect: (
    trackId: string,
    clipId: string,
    effectId: string,
    patch: Partial<Omit<EffectInstance, 'id'>>,
  ) => void
  updateTrackEffect: (
    trackId: string,
    effectId: string,
    patch: Partial<Omit<EffectInstance, 'id'>>,
  ) => void
  setCatalogSearch: (trackKind: CatalogTrackKind, query: string) => void
  fetchCatalog: () => Promise<void>
  clearCatalogAddFeedback: () => void

  // ---- Theme --------------------------------------------------------------
  toggleThemeMode: () => void
  setThemeMode: (mode: ThemeMode) => void

  // ---- Layout -------------------------------------------------------------
  setLayoutPrefs: (patch: Partial<LayoutPrefs>) => void
  toggleFavoriteClipType: (clipType: string) => void
  toggleLogsPanel: () => void
  toggleSettingsPanel: () => void
  setSettingsPanelOpen: (open: boolean) => void
  setAppView: (view: AppView) => void
  setFocusedJobId: (id: string | null) => void
  openJobsView: (jobId?: string | null) => void
  backToEditor: () => void
  setAppSettings: (patch: Partial<AppSettings>) => void
  setApiConnectionStatus: (status: ApiConnectionStatus) => void
  setApiRetryInSeconds: (seconds: number | null) => void
  setComposeHealth: (health: ComposeHealth | null) => void
  setPexelsAvailable: (available: boolean | null) => void
  setFfmpegAvailable: (available: boolean | null) => void
  requestApiRetryNow: () => void
  appendEventLog: (level: EventLogEntry['level'], message: string) => void
  clearEventLogs: () => void
  reconcilePluginAvailability: (availableClipTypes: string[]) => {
    reactivatedClips: number
    stillMissingClips: number
    reactivatedProjectSettings: number
    stillMissingProjectSettings: number
  }

  // ---- Project lifecycle --------------------------------------------------
  loadProject: (
    state: Omit<
      Pick<
        ProjectState,
        | 'meta'
        | 'typography'
        | 'colors'
        | 'paletteSource'
        | 'tracks'
        | 'sounds'
        | 'timelineLayout'
        | 'projectSettings'
        | 'importBundleId'
      >,
      never
    >,
  ) => void
  resetProject: () => void
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function newId(prefix: string): string {
  return `${prefix}-${Math.random().toString(36).slice(2, 9)}`
}

function cloneClipForDuplicate(source: Clip): Clip {
  return {
    ...source,
    id: newId('el'),
    params: { ...source.params },
    effects: source.effects?.map((fx) => ({
      ...fx,
      id: newId('fx'),
      params: { ...fx.params },
    })),
  }
}

const DEFAULT_META: ProjectMeta = {
  title: 'Untitled',
  author: '',
  fps: 30,
  duration: 30,
  width: 1080,
  height: 1920,
  exportQuality: 'master',
}

const DEFAULT_LAYOUT_PREFS: LayoutPrefs = {
  leftWidthPct: 18,
  rightWidthPct: 28,
  previewHeightPct: 40,
  leftCollapsed: false,
  rightCollapsed: true,
}

function clamp(n: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, n))
}

function sanitizeLayoutPrefs(prefs: Partial<LayoutPrefs> | null | undefined): LayoutPrefs {
  const next = { ...DEFAULT_LAYOUT_PREFS, ...(prefs ?? {}) }
  const finiteOr = (n: number, fallback: number) =>
    Number.isFinite(n) ? n : fallback
  return {
    leftWidthPct: clamp(finiteOr(next.leftWidthPct, DEFAULT_LAYOUT_PREFS.leftWidthPct), 12, 28),
    rightWidthPct: clamp(finiteOr(next.rightWidthPct, DEFAULT_LAYOUT_PREFS.rightWidthPct), 20, 38),
    previewHeightPct: clamp(
      finiteOr(next.previewHeightPct, DEFAULT_LAYOUT_PREFS.previewHeightPct),
      8,
      50
    ),
    leftCollapsed: Boolean(next.leftCollapsed),
    rightCollapsed: Boolean(next.rightCollapsed),
  }
}

function readAppLayoutPrefs(): LayoutPrefs {
  try {
    const raw = localStorage.getItem('layout:app')
    const parsed = raw ? (JSON.parse(raw) as Partial<LayoutPrefs>) : undefined
    // rightCollapsed is selection-driven, not a persistent user pref — always start collapsed
    return sanitizeLayoutPrefs({ ...parsed, rightCollapsed: true })
  } catch {
    return { ...DEFAULT_LAYOUT_PREFS }
  }
}

function writeAppLayoutPrefs(prefs: LayoutPrefs): void {
  localStorage.setItem('layout:app', JSON.stringify(prefs))
}

function readAppFavoriteClipTypes(): string[] {
  try {
    const raw = localStorage.getItem('favorites:app')
    const parsed = raw ? (JSON.parse(raw) as unknown) : []
    if (!Array.isArray(parsed)) return []
    return parsed.filter((v): v is string => typeof v === 'string')
  } catch {
    return []
  }
}

function writeAppFavoriteClipTypes(clipTypes: string[]): void {
  localStorage.setItem('favorites:app', JSON.stringify(clipTypes))
}

const DEFAULT_APP_SETTINGS: AppSettings = {
  locale: 'en',
  previewDebounceMs: 400,
  previewClipLoopSeconds: 8,
  clipPreviewMode: 'clip',
  thumbnailExportResolution: 'full',
  renderParallelism: 'single',
  videoEncoder: 'auto',
}

function readClipPreviewModeFromSettings(
  raw: Partial<AppSettings>,
): ClipPreviewMode {
  return normalizeClipPreviewMode(raw.clipPreviewMode)
}

function readPreviewClipLoopSeconds(
  raw: Partial<AppSettings>,
): number {
  const value = raw.previewClipLoopSeconds
  return typeof value === 'number' ? value : DEFAULT_APP_SETTINGS.previewClipLoopSeconds
}

function sanitizeAppSettings(raw: Partial<AppSettings> | null | undefined): AppSettings {
  const next = { ...(raw ?? {}) }
  return {
    locale:
      next.locale === 'es' || next.locale === 'zh-CN' || next.locale === 'en' || next.locale === 'ja'
        ? next.locale
        : 'en',
    previewDebounceMs: clamp(next.previewDebounceMs ?? DEFAULT_APP_SETTINGS.previewDebounceMs, 100, 2000),
    previewClipLoopSeconds: clamp(
      readPreviewClipLoopSeconds(next),
      1,
      15,
    ),
    clipPreviewMode: readClipPreviewModeFromSettings(next),
    thumbnailExportResolution:
      next.thumbnailExportResolution === 'preview' ? 'preview' : 'full',
    renderParallelism: next.renderParallelism === 'multi' ? 'multi' : 'single',
    videoEncoder:
      next.videoEncoder === 'cpu' || next.videoEncoder === 'nvenc'
        ? next.videoEncoder
        : 'auto',
  }
}

function appSettingsForProjectLoad(current: AppSettings): AppSettings {
  const next = sanitizeAppSettings({ ...current, clipPreviewMode: 'clip' })
  writeAppSettings(next)
  return next
}

function normalizeProjectSetting(raw: ProjectSetting): ProjectSetting {
  const clip_type =
    typeof raw.clip_type === 'string' && raw.clip_type.trim() ? raw.clip_type : ''
  return { ...raw, clip_type }
}

function readAppSettings(): AppSettings {
  try {
    const raw = localStorage.getItem('app:settings')
    return sanitizeAppSettings(raw ? (JSON.parse(raw) as Partial<AppSettings>) : undefined)
  } catch {
    return { ...DEFAULT_APP_SETTINGS }
  }
}

function hasPersistedAppSettings(): boolean {
  try {
    return localStorage.getItem('app:settings') !== null
  } catch {
    return false
  }
}

function writeAppSettings(settings: AppSettings): void {
  localStorage.setItem('app:settings', JSON.stringify(settings))
}

// ---------------------------------------------------------------------------
// Undo history (zundo temporal) — slice comparison
// ---------------------------------------------------------------------------

/** What zundo `partialize` keeps in each history entry. */
type ProjectHistorySlice = Pick<
  ProjectState,
  'meta' | 'typography' | 'colors' | 'paletteSource' | 'tracks' | 'sounds' | 'timelineLayout' | 'projectSettings'
>

function projectHistorySliceEqual(a: ProjectHistorySlice, b: ProjectHistorySlice): boolean {
  // Value-based: zundo would otherwise push a new entry on every `set()` even
  // when only `selection` / theme / etc. changed. Undo would then pop that
  // noise first and leave the real edit (e.g. add track) in place.
  return JSON.stringify(a) === JSON.stringify(b)
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const useProjectStore = create<ProjectState>()(
  temporal(
    (set, get) => ({
      meta: { ...DEFAULT_META },
      typography: cloneFontPalette(DEFAULT_FONT_PALETTE),
      colors: cloneJobColors(DEFAULT_JOB_COLORS),
      paletteSource: { ...DEFAULT_PALETTE_SOURCE },
      projectSettings: [],
      tracks: [],
      sounds: [],
      timelineLayout: [],
      importBundleId: null,
      selection: null,
      pluginPicker: null,
      composePanelOpen: false,
      composeSessionId: null,
      composeMessages: [],
      composeLastProject: null,
      catalogClips: [],
      catalogEffects: [],
      catalogLoadStatus: 'idle',
      catalogSearchByKind: { skia: '', gl: '', post: '' },
      catalogAddFeedback: null,
      projectLoadEpoch: 0,
      catalogDetailCache: {},
      fontCatalog: FALLBACK_FONT_CATALOG,
      fontCatalogFallback: true,
      themePresets: FALLBACK_THEME_PRESETS,
      themePresetsFallback: true,
      serverConfig: fallbackServerConfig(),
      serverConfigWarned: false,
      themeMode: (localStorage.getItem('themeMode') as ThemeMode | null) ??
        ((localStorage.getItem('theme') as 'dark' | 'light' | null) ?? 'dark'),
      appLayoutPrefs: readAppLayoutPrefs(),
      appFavoriteClipTypes: readAppFavoriteClipTypes(),
      apiConnectionStatus: 'checking',
      apiRetryInSeconds: null,
      apiRetryNonce: 0,
      composeHealth: null,
      pexelsAvailable: null,
      ffmpegAvailable: null,
      showLogsPanel: false,
      showSettingsPanel: false,
      appView: 'editor',
      focusedJobId: null,
      appSettings: readAppSettings(),
      eventLogs: [],
      prepareWarnings: [],
      setPrepareWarnings: (items) => set({ prepareWarnings: items }),
      isPlaying: false,
      setIsPlaying: (playing) => set({ isPlaying: playing }),
      previewTime: 0,
      setPreviewTime: (t) => set({ previewTime: Math.max(0, t) }),
      previewMuted: false,
      setPreviewMuted: (muted) => set({ previewMuted: muted }),
      togglePreviewMuted: () => set((s) => ({ previewMuted: !s.previewMuted })),
      platformPresetId: DEFAULT_PLATFORM_PRESET_ID,

      // ---- Meta -----------------------------------------------------------
      setMeta: (patch) =>
        set((s) => {
          const meta = { ...s.meta, ...patch }
          let platformPresetId = s.platformPresetId
          if (
            platformPresetId &&
            (patch.width !== undefined || patch.height !== undefined || patch.fps !== undefined)
          ) {
            const preset = getPlatformPreset(platformPresetId)
            if (
              !preset ||
              meta.width !== preset.width ||
              meta.height !== preset.height ||
              meta.fps !== preset.fps
            ) {
              platformPresetId = null
            }
          }
          return { meta, platformPresetId }
        }),

      setPlatformPresetId: (id) => set({ platformPresetId: id }),

      applyPlatformPreset: (id) => {
        const preset = getPlatformPreset(id)
        if (!preset) return
        set((s) => ({
          platformPresetId: id,
          meta: {
            ...s.meta,
            width: preset.width,
            height: preset.height,
            fps: preset.fps,
            duration: Math.min(
              s.meta.duration > preset.maxSec ? preset.maxSec : s.meta.duration,
              s.serverConfig.maxDurationS,
            ),
          },
        }))
      },

      setSansFamily: (family) =>
        set((s) => ({
          typography: applyGlobalFamilies(
            s.typography,
            family,
            monoFamilyFromPalette(s.typography),
          ),
        })),

      setMonoFamily: (family) =>
        set((s) => ({
          typography: applyGlobalFamilies(
            s.typography,
            sansFamilyFromPalette(s.typography),
            family,
          ),
        })),

      setRoleTypography: (role, patch) =>
        set((s) => ({
          typography: {
            ...s.typography,
            [role]: { ...s.typography[role], ...patch },
          },
        })),

      fetchFontCatalog: async () => {
        const { catalog, fromFallback } = await fetchFontCatalogApi()
        set({ fontCatalog: catalog, fontCatalogFallback: fromFallback })
      },

      fetchThemePresets: async () => {
        try {
          const presets = await fetchThemePresets()
          set({ themePresets: presets, themePresetsFallback: false })
        } catch {
          set({ themePresets: FALLBACK_THEME_PRESETS, themePresetsFallback: true })
        }
      },

      fetchServerConfig: async () => {
        try {
          const payload = await apiGet<ServerConfigPayload>('/config')
          const serverConfig = parseServerConfigPayload(payload)
          set((s) => {
            const reconciled = reconcileMetaWithRenderLimits(
              s.meta,
              s.platformPresetId,
              serverConfig,
            )
            const next: {
              serverConfig: typeof serverConfig
              serverConfigWarned: boolean
              meta: typeof reconciled.meta
              platformPresetId: typeof reconciled.platformPresetId
              appSettings?: AppSettings
            } = {
              serverConfig,
              serverConfigWarned: false,
              meta: reconciled.meta,
              platformPresetId: reconciled.platformPresetId,
            }
            if (!hasPersistedAppSettings()) {
              const appSettings = sanitizeAppSettings({
                ...s.appSettings,
                locale: serverConfig.defaultLocale,
              })
              writeAppSettings(appSettings)
              next.appSettings = appSettings
            }
            return next
          })
        } catch {
          set({ serverConfig: fallbackServerConfig() })
          const state = useProjectStore.getState()
          if (state.serverConfigWarned) return
          set({ serverConfigWarned: true })
          const locale = state.appSettings.locale
          const localized = messages[locale as keyof typeof messages] as
            | (typeof messages.en)
            | undefined
          state.appendEventLog(
            'warn',
            localized?.event_server_config_unavailable
              ?? messages.en.event_server_config_unavailable,
          )
        }
      },

      applyNamedPreset: (theme, variant, colors) =>
        set({
          colors: cloneJobColors(colors),
          paletteSource: { type: 'named', theme, variant },
        }),

      applyExtractedPalette: (colors, filename) =>
        set({
          colors: cloneJobColors(colors),
          paletteSource: { type: 'extracted', filename },
        }),

      applyCustomPalette: (colors) =>
        set({
          colors: cloneJobColors(colors),
          paletteSource: { type: 'custom' },
        }),

      setJobColor: (token, hex) =>
        set((s) => ({
          colors: { ...s.colors, [token]: hex },
          paletteSource: { type: 'custom' },
        })),

      // ---- Tracks ---------------------------------------------------------
      addTrack: (track) =>
        set((s) => ({
          tracks: [...s.tracks, track],
          timelineLayout: [{ kind: 'track', id: track.id }, ...s.timelineLayout],
        })),

      updateTrack: (trackId, patch) =>
        set((s) => ({
          tracks: s.tracks.map((t) => (t.id === trackId ? { ...t, ...patch } : t)),
        })),

      removeTrack: (trackId) =>
        set((s) => ({
          tracks: s.tracks.filter((t) => t.id !== trackId),
          timelineLayout: removeFromLayout(s.timelineLayout, 'track', trackId),
          selection:
            (s.selection?.kind === 'track' && s.selection.trackId === trackId) ||
            (isClipSelection(s.selection) && s.selection.trackId === trackId)
              ? null
              : s.selection,
        })),

      duplicateTrack: (trackId) =>
        set((s) => {
          const source = s.tracks.find((t) => t.id === trackId)
          if (!source) return s
          const clone: Track = {
            ...source,
            id: newId('track'),
            label: `${source.label} Copy`,
            clips: source.clips.map((el) => ({
              ...el,
              id: newId('el'),
            })),
          }
          const idx = s.tracks.findIndex((t) => t.id === trackId)
          const tracks = [...s.tracks]
          tracks.splice(idx + 1, 0, clone)
          const layout = [...s.timelineLayout]
          const layoutIdx = layout.findIndex((e) => e.kind === 'track' && e.id === trackId)
          if (layoutIdx !== -1) {
            layout.splice(layoutIdx, 0, { kind: 'track', id: clone.id })
          } else {
            layout.unshift({ kind: 'track', id: clone.id })
          }
          return { tracks, timelineLayout: layout }
        }),

      toggleTrackEnabled: (trackId) =>
        set((s) => ({
          tracks: s.tracks.map((t) =>
            t.id === trackId ? { ...t, enabled: !t.enabled } : t
          ),
        })),

      reorderTracks: (fromIndex, toIndex) =>
        set((s) => {
          const tracks = [...s.tracks]
          const [moved] = tracks.splice(fromIndex, 1)
          tracks.splice(toIndex, 0, moved)
          return { tracks }
        }),

      // ---- Sounds ---------------------------------------------------------
      addSound: (sound) =>
        set((s) => ({
          sounds: [...s.sounds, sound],
          timelineLayout: [{ kind: 'sound', id: sound.id }, ...s.timelineLayout],
        })),

      updateSound: (soundId, patch) =>
        set((s) => ({
          sounds: s.sounds.map((snd) =>
            snd.id === soundId ? sanitizeSoundPatch(snd, patch) : snd,
          ),
        })),

      applyFitProjectToSound: (soundId, newDuration) =>
        set((s) => {
          if (!s.sounds.some((snd) => snd.id === soundId)) return s
          const duration = Math.max(newDuration, 1 / s.meta.fps)
          return {
            ...s,
            meta: { ...s.meta, duration },
            sounds: s.sounds.map((snd) =>
              snd.id === soundId
                ? { ...snd, start: 0, duration: null }
                : snd,
            ),
            previewTime: Math.min(s.previewTime, duration),
          }
        }),

      removeSound: (soundId) =>
        set((s) => ({
          sounds: s.sounds.filter((snd) => snd.id !== soundId),
          timelineLayout: removeFromLayout(s.timelineLayout, 'sound', soundId),
          selection:
            s.selection?.kind === 'sound' && s.selection.soundId === soundId
              ? null
              : s.selection,
        })),

      duplicateSound: (soundId) =>
        set((s) => {
          const source = s.sounds.find((snd) => snd.id === soundId)
          if (!source) return s
          const clone: Sound = {
            ...source,
            id: newId('sound'),
            bus: `${source.bus} Copy`,
          }
          const sounds = [...s.sounds, clone]
          const layout = [...s.timelineLayout]
          const layoutIdx = layout.findIndex((e) => e.kind === 'sound' && e.id === soundId)
          if (layoutIdx !== -1) {
            layout.splice(layoutIdx, 0, { kind: 'sound', id: clone.id })
          } else {
            layout.unshift({ kind: 'sound', id: clone.id })
          }
          return { sounds, timelineLayout: layout }
        }),

      toggleSoundEnabled: (soundId) =>
        set((s) => ({
          sounds: s.sounds.map((snd) => {
            if (snd.id !== soundId) return snd
            if (!snd.bus.trim() || !snd.source.trim()) return { ...snd, enabled: false }
            return { ...snd, enabled: !snd.enabled }
          }),
        })),

      reorderTimelineLayout: (fromIndex, toIndex) =>
        set((s) => {
          const layout = [...resolveTimelineLayout(s.timelineLayout, s.tracks, s.sounds)]
          const [moved] = layout.splice(fromIndex, 1)
          layout.splice(toIndex, 0, moved)
          return {
            timelineLayout: layout,
            tracks: tracksOrderFromLayout(layout, s.tracks),
            sounds: soundsOrderFromLayout(layout, s.sounds),
          }
        }),

      // ---- Clips -------------------------------------------------------
      addClip: (trackId, clip) =>
        set((s) => ({
          tracks: s.tracks.map((t) => {
            if (t.id !== trackId) return t
            const clips = [...t.clips, clip]
            const bandPatch =
              clips.length === 2 ? bandLayoutPatchForSecondClip(t) : null
            return {
              ...t,
              clips,
              ...(bandPatch ?? {}),
            }
          }),
        })),

      addCatalogClip: (trackId, clipType, label) => {
        set((s) => {
          const track = s.tracks.find((t) => t.id === trackId)
          if (!track) return s

          const clip: Clip = {
            id: newId('el'),
            clip_type: clipType,
            label,
            start: 0,
            duration: null,
            enabled: true,
            params: {},
          }

          const isPost = (track.trackType ?? 'skia') === 'post'
          const clips =
            isPost && track.clips.length >= 1
              ? [clip]
              : [...track.clips, clip]
          const bandPatch =
            !isPost && clips.length === 2
              ? bandLayoutPatchForSecondClip(track)
              : null

          return {
            tracks: s.tracks.map((t) =>
              t.id === trackId
                ? { ...t, clips, ...(bandPatch ?? {}) }
                : t,
            ),
            catalogAddFeedback: {
              trackId,
              clipId: clip.id,
              clipType,
            },
          }
        });
        const fb = useProjectStore.getState().catalogAddFeedback
        if (fb) {
          void useProjectStore.getState().hydrateClipDefaults(
            fb.trackId,
            fb.clipId,
            fb.clipType,
          )
        }
      },

      applyTimelineImportBatch: (batch) => {
        if (batch.visualTracks.length === 0 && batch.sounds.length === 0) return null

        const newTracks: Track[] = batch.visualTracks.map((item) => {
          const trackId = newId('track')
          const clipId = newId('el')
          return {
            id: trackId,
            label: item.trackLabel,
            enabled: true,
            disableMode: 'bypass_compute',
            start: 0,
            duration: null,
            layout: 'fill',
            trackType: 'skia',
            clips: [
              {
                id: clipId,
                clip_type: item.clipType ?? '',
                label: item.clipLabel,
                start: 0,
                duration: item.clipDuration ?? null,
                enabled: true,
                params: item.params,
              },
            ],
          }
        })

        const newSounds: Sound[] = batch.sounds.map((item) => ({
          id: newId('sound'),
          ...item,
        }))

        const layoutEntries: TimelineLayoutEntry[] = batch.layoutOrder.map((entry) => {
          if (entry.kind === 'track') {
            const track = newTracks[entry.trackIndex]!
            return { kind: 'track' as const, id: track.id }
          }
          const sound = newSounds[entry.soundIndex]!
          return { kind: 'sound' as const, id: sound.id }
        })

        const last = batch.layoutOrder[batch.layoutOrder.length - 1]
        let frontTrackId: string | undefined
        let frontClipId: string | undefined
        let frontSoundId: string | undefined
        let selection: ProjectState['selection'] = null
        let catalogAddFeedback: CatalogAddFeedback | null = null

        if (last?.kind === 'track') {
          const track = newTracks[last.trackIndex]!
          const clip = track.clips[0]!
          frontTrackId = track.id
          frontClipId = clip.id
          selection = {
            kind: 'clip',
            trackId: track.id,
            clipId: clip.id,
          }
          catalogAddFeedback = {
            trackId: track.id,
            clipId: clip.id,
            clipType: clip.clip_type,
          }
        } else if (last?.kind === 'sound') {
          const sound = newSounds[last.soundIndex]!
          frontSoundId = sound.id
          selection = { kind: 'sound', soundId: sound.id }
        }

        set((s) => ({
          tracks: [...s.tracks, ...newTracks],
          sounds: [...s.sounds, ...newSounds],
          timelineLayout: [...layoutEntries].reverse().concat(s.timelineLayout),
          selection,
          catalogAddFeedback,
        }))

        return { frontTrackId, frontClipId, frontSoundId }
      },

      ensureCatalogDetail: async (clipType: string, kind: 'clip' | 'effect' = 'clip') => {
        const state = useProjectStore.getState()
        const locale = state.appSettings.locale
        const cacheKey = catalogDetailCacheKey(clipType, locale)
        const cached = state.catalogDetailCache[cacheKey]
        if (cached) return cached

        const segment = kind === 'effect' ? 'effects' : 'clips'
        try {
          const detail = await apiGet<ClipCatalogDetail>(
            `/catalog/${segment}/${encodeURIComponent(clipType)}?lang=${encodeURIComponent(locale)}`,
          )
          set((s) => ({
            catalogDetailCache: { ...s.catalogDetailCache, [cacheKey]: detail },
          }))
          return detail
        } catch {
          state.appendEventLog(
            'warn',
            `Could not load clip UI for ${clipType}.`,
          )
          return null
        }
      },

      hydrateClipDefaults: async (
        trackId: string,
        clipId: string,
        clipType: string,
      ) => {
        const state = useProjectStore.getState()
        const track = state.tracks.find((t) => t.id === trackId)
        const clip = track?.clips.find((el) => el.id === clipId)
        if (!clip || !paramsNeedDefaultsHydration(clip.params)) {
          return true
        }

        const locale = state.appSettings.locale
        const cacheKey = catalogDetailCacheKey(clipType, locale)
        let detail = state.catalogDetailCache[cacheKey]

        if (!detail) {
          try {
            detail = await apiGet<ClipCatalogDetail>(
              `/catalog/clips/${encodeURIComponent(clipType)}?lang=${encodeURIComponent(locale)}`,
            )
            set((s) => ({
              catalogDetailCache: { ...s.catalogDetailCache, [cacheKey]: detail! },
            }))
          } catch (err) {
            const detail =
              err instanceof ApiHttpError
                ? err.detail
                : err instanceof Error
                  ? err.message
                  : undefined
            state.appendEventLog(
              'warn',
              detail
                ? `Could not load parameter defaults for ${clipType}: ${detail}`
                : `Could not load parameter defaults for ${clipType}.`,
            )
            return false
          }
        }

        useProjectStore.getState().updateClip(trackId, clipId, {
          params: { ...detail.defaults },
        })
        return true
      },

      clearCatalogAddFeedback: () => set({ catalogAddFeedback: null }),

      updateClip: (
        trackId: string,
        clipId: string,
        patch: Partial<Omit<Clip, 'id'>>,
      ) =>
        set((s) => ({
          tracks: s.tracks.map((t) =>
            t.id !== trackId
              ? t
              : {
                  ...t,
                  clips: t.clips.map((el) =>
                    el.id === clipId ? { ...el, ...patch } : el
                  ),
                }
          ),
        })),

      toggleClipEnabled: (trackId, clipId) =>
        set((s) => ({
          tracks: s.tracks.map((t) =>
            t.id !== trackId
              ? t
              : {
                  ...t,
                  clips: t.clips.map((el) =>
                    el.id === clipId ? { ...el, enabled: !el.enabled } : el
                  ),
                }
          ),
        })),

      applyClipPreset: (trackId, clipId, values) =>
        set((s) => ({
          tracks: s.tracks.map((t) =>
            t.id !== trackId
              ? t
              : {
                  ...t,
                  clips: t.clips.map((el) =>
                    el.id === clipId
                      ? { ...el, params: { ...el.params, ...values } }
                      : el
                  ),
                }
          ),
        })),

      removeClip: (trackId, clipId) =>
        set((s) => ({
          tracks: s.tracks.map((t) =>
            t.id !== trackId
              ? t
              : { ...t, clips: t.clips.filter((el) => el.id !== clipId) }
          ),
          selection:
            isClipSelection(s.selection) &&
            s.selection.trackId === trackId &&
            s.selection.clipId === clipId
              ? null
              : s.selection,
        })),

      duplicateClip: (trackId, clipId) => {
        get().insertClipCloneAfter(trackId, clipId)
      },

      insertClipCloneAfter: (trackId, afterClipId, patch) => {
        const s = get()
        const track = s.tracks.find((t) => t.id === trackId)
        if (!track) return null
        if ((track.trackType ?? 'skia') === 'post') return null
        if (!canAddClipToTrack(track, s.serverConfig)) return null

        const sourceIndex = track.clips.findIndex((el) => el.id === afterClipId)
        if (sourceIndex === -1) return null

        const source = track.clips[sourceIndex]!
        const clone = cloneClipForDuplicate(source)
        const clip: Clip = {
          ...clone,
          ...patch,
          params: { ...clone.params, ...(patch?.params ?? {}) },
          effects: patch?.effects ?? clone.effects,
        }
        const clips = [...track.clips]
        clips.splice(sourceIndex + 1, 0, clip)
        const bandPatch =
          clips.length === 2 ? bandLayoutPatchForSecondClip(track) : null

        set({
          tracks: s.tracks.map((t) =>
            t.id === trackId
              ? { ...t, clips, ...(bandPatch ?? {}) }
              : t,
          ),
          selection: { kind: 'clip', trackId, clipId: clip.id },
          catalogAddFeedback: {
            trackId,
            clipId: clip.id,
            clipType: clip.clip_type,
          },
        })
        return clip.id
      },

      moveClip: (fromTrackId, toTrackId, clipId) =>
        set((s) => {
          if (fromTrackId === toTrackId) return s
          const fromTrack = s.tracks.find((t) => t.id === fromTrackId)
          const toTrack = s.tracks.find((t) => t.id === toTrackId)
          if (!fromTrack || !toTrack) return s
          const clip = fromTrack.clips.find((el) => el.id === clipId)
          if (!clip) return s

          const isPostDest = (toTrack.trackType ?? 'skia') === 'post'
          const newFromClips = fromTrack.clips.filter((el) => el.id !== clipId)
          const newToClips = isPostDest
            ? [clip]
            : [...toTrack.clips, clip]
          const toBandPatch =
            !isPostDest && newToClips.length === 2
              ? bandLayoutPatchForSecondClip(toTrack)
              : null

          return {
            tracks: s.tracks.map((t) => {
              if (t.id === fromTrackId) {
                return { ...t, clips: newFromClips }
              }
              if (t.id === toTrackId) {
                return { ...t, clips: newToClips, ...(toBandPatch ?? {}) }
              }
              return t
            }),
            selection: { kind: 'clip', trackId: toTrackId, clipId },
            pluginPicker: null,
          }
        }),

      reorderClips: (trackId, fromIndex, toIndex) =>
        set((s) => ({
          tracks: s.tracks.map((t) => {
            if (t.id !== trackId) return t
            const clips = [...t.clips]
            const [moved] = clips.splice(fromIndex, 1)
            clips.splice(toIndex, 0, moved!)
            return { ...t, clips }
          }),
        })),

      swapTrackClips: (trackId) =>
        set((s) => ({
          tracks: s.tracks.map((t) => {
            if (t.id !== trackId || t.clips.length !== 2) return t
            return { ...t, clips: [t.clips[1]!, t.clips[0]!] }
          }),
        })),

      // ---- Project settings -----------------------------------------------
      addProjectSetting: (setting) => set((s) => ({ projectSettings: [...s.projectSettings, setting] })),

      updateProjectSetting: (projectSettingId, patch) =>
        set((s) => ({
          projectSettings: s.projectSettings.map((n) => (n.id === projectSettingId ? { ...n, ...patch } : n)),
        })),

      removeProjectSetting: (projectSettingId) =>
        set((s) => ({
          projectSettings: s.projectSettings.filter((n) => n.id !== projectSettingId),
          selection:
            s.selection?.kind === 'projectSetting' && s.selection.projectSettingId === projectSettingId
              ? null
              : s.selection,
        })),

      // ---- Selection ------------------------------------------------------
      select: (selection) => set({ selection, pluginPicker: null }),
      clearSelection: () => set({ selection: null, pluginPicker: null }),

      openPluginPicker: (trackId, trackKind) =>
        set({
          pluginPicker: { trackId, trackKind, mode: 'clip' },
          composePanelOpen: false,
        }),

      openEffectPicker: (trackId, clipId, effectBackend) => {
        void get().fetchCatalog()
        set({
          pluginPicker: {
            trackId,
            mode: 'effect',
            effectScope: 'clip',
            clipId,
            effectBackend,
          },
          selection: { kind: 'clip', trackId, clipId },
          composePanelOpen: false,
        })
      },

      openTrackEffectPicker: (trackId, effectBackend) => {
        void get().fetchCatalog()
        set({
          pluginPicker: {
            trackId,
            mode: 'effect',
            effectScope: 'track',
            effectBackend: effectBackend ?? 'gl',
          },
          selection: { kind: 'track', trackId },
          composePanelOpen: false,
        })
      },

      closePluginPicker: () => set({ pluginPicker: null }),

      openComposePanel: () =>
        set({
          composePanelOpen: true,
          pluginPicker: null,
        }),

      closeComposePanel: () => set({ composePanelOpen: false }),

      setComposeSessionId: (sessionId) => set({ composeSessionId: sessionId }),

      appendComposeMessages: (messages) =>
        set((s) => ({ composeMessages: [...s.composeMessages, ...messages] })),

      setComposeLastProject: (project) => set({ composeLastProject: project }),

      clearComposeChat: () =>
        set({
          composeSessionId: null,
          composeMessages: [],
          composeLastProject: null,
        }),

      setCatalogSearch: (trackKind: CatalogTrackKind, query: string) =>
        set((s) => ({
          catalogSearchByKind: { ...s.catalogSearchByKind, [trackKind]: query },
        })),

      fetchCatalog: async () => {
        const locale = useProjectStore.getState().appSettings.locale
        set({ catalogLoadStatus: 'loading' })
        try {
          const [clips, effects] = await Promise.all([
            apiGet<CatalogClipItem[]>(
              `/catalog/clips?lang=${encodeURIComponent(locale)}`,
            ),
            apiGet<CatalogEffectItem[]>(
              `/catalog/effects?lang=${encodeURIComponent(locale)}`,
            ),
          ])
          set({
            catalogClips: clips,
            catalogEffects: effects.map(normalizeCatalogEffect),
            catalogLoadStatus: 'ready',
          })
          useProjectStore.getState().reconcilePluginAvailability(
            clips.map((n) => n.clip_type),
          )
        } catch {
          set({ catalogClips: [], catalogEffects: [], catalogLoadStatus: 'error' })
        }
      },

      addCatalogEffect: (trackId, clipId, effectType, label) => {
        set((s) => ({
          tracks: s.tracks.map((t) => {
            if (t.id !== trackId) return t
            return {
              ...t,
              clips: t.clips.map((el) => {
                if (el.id !== clipId) return el
                const effects = [...(el.effects ?? [])]
                if (effects.length >= 3) return el
                effects.push({
                  id: newId('fx'),
                  effect_type: effectType,
                  label,
                  enabled: true,
                  params: {},
                })
                return { ...el, effects }
              }),
            }
          }),
          pluginPicker: null,
        }))
      },

      addCatalogTrackEffect: (trackId, effectType, label) => {
        set((s) => ({
          tracks: s.tracks.map((t) => {
            if (t.id !== trackId) return t
            const effects = [...(t.effects ?? [])]
            if (effects.length >= 3) return t
            effects.push({
              id: newId('fx'),
              effect_type: effectType,
              label,
              enabled: true,
              params: {},
            })
            return { ...t, effects }
          }),
          pluginPicker: null,
        }))
      },

      removeEffect: (trackId, clipId, effectId) =>
        set((s) => ({
          tracks: s.tracks.map((t) =>
            t.id !== trackId
              ? t
              : {
                  ...t,
                  clips: t.clips.map((el) =>
                    el.id !== clipId
                      ? el
                      : {
                          ...el,
                          effects: (el.effects ?? []).filter((fx) => fx.id !== effectId),
                        },
                  ),
                },
          ),
        })),

      removeTrackEffect: (trackId, effectId) =>
        set((s) => ({
          tracks: s.tracks.map((t) =>
            t.id !== trackId
              ? t
              : {
                  ...t,
                  effects: (t.effects ?? []).filter((fx) => fx.id !== effectId),
                },
          ),
        })),

      reorderEffects: (trackId, clipId, fromIndex, toIndex) =>
        set((s) => ({
          tracks: s.tracks.map((t) => {
            if (t.id !== trackId) return t
            return {
              ...t,
              clips: t.clips.map((el) => {
                if (el.id !== clipId) return el
                const effects = [...(el.effects ?? [])]
                if (
                  fromIndex < 0 ||
                  toIndex < 0 ||
                  fromIndex >= effects.length ||
                  toIndex >= effects.length
                ) {
                  return el
                }
                const [item] = effects.splice(fromIndex, 1)
                effects.splice(toIndex, 0, item)
                return { ...el, effects }
              }),
            }
          }),
        })),

      reorderTrackEffects: (trackId, fromIndex, toIndex) =>
        set((s) => ({
          tracks: s.tracks.map((t) => {
            if (t.id !== trackId) return t
            const effects = [...(t.effects ?? [])]
            if (
              fromIndex < 0 ||
              toIndex < 0 ||
              fromIndex >= effects.length ||
              toIndex >= effects.length
            ) {
              return t
            }
            const [item] = effects.splice(fromIndex, 1)
            effects.splice(toIndex, 0, item)
            return { ...t, effects }
          }),
        })),

      toggleEffectEnabled: (trackId, clipId, effectId) =>
        set((s) => ({
          tracks: s.tracks.map((t) =>
            t.id !== trackId
              ? t
              : {
                  ...t,
                  clips: t.clips.map((el) =>
                    el.id !== clipId
                      ? el
                      : {
                          ...el,
                          effects: (el.effects ?? []).map((fx) =>
                            fx.id !== effectId
                              ? fx
                              : { ...fx, enabled: fx.enabled === false ? true : false },
                          ),
                        },
                  ),
                },
          ),
        })),

      toggleTrackEffectEnabled: (trackId, effectId) =>
        set((s) => ({
          tracks: s.tracks.map((t) =>
            t.id !== trackId
              ? t
              : {
                  ...t,
                  effects: (t.effects ?? []).map((fx) =>
                    fx.id !== effectId
                      ? fx
                      : { ...fx, enabled: fx.enabled === false ? true : false },
                  ),
                },
          ),
        })),

      updateEffect: (trackId, clipId, effectId, patch) =>
        set((s) => ({
          tracks: s.tracks.map((t) =>
            t.id !== trackId
              ? t
              : {
                  ...t,
                  clips: t.clips.map((el) =>
                    el.id !== clipId
                      ? el
                      : {
                          ...el,
                          effects: (el.effects ?? []).map((fx) =>
                            fx.id !== effectId ? fx : { ...fx, ...patch },
                          ),
                        },
                  ),
                },
          ),
        })),

      updateTrackEffect: (trackId, effectId, patch) =>
        set((s) => ({
          tracks: s.tracks.map((t) =>
            t.id !== trackId
              ? t
              : {
                  ...t,
                  effects: (t.effects ?? []).map((fx) =>
                    fx.id !== effectId ? fx : { ...fx, ...patch },
                  ),
                },
          ),
        })),

      // ---- Theme ----------------------------------------------------------
      toggleThemeMode: () =>
        set((s) => {
          const next: ThemeMode =
            s.themeMode === 'dark'
              ? 'light'
              : s.themeMode === 'light'
                ? 'system'
                : 'dark'
          localStorage.setItem('themeMode', next)
          return { themeMode: next }
        }),
      setThemeMode: (mode: ThemeMode) =>
        set(() => {
          localStorage.setItem('themeMode', mode)
          return { themeMode: mode }
        }),

      // ---- Layout ---------------------------------------------------------
      setLayoutPrefs: (patch: Partial<LayoutPrefs>) =>
        set((s) => {
          const next = sanitizeLayoutPrefs({ ...s.appLayoutPrefs, ...patch })
          writeAppLayoutPrefs(next)
          return { appLayoutPrefs: next }
        }),

      toggleFavoriteClipType: (clipType: string) =>
        set((s) => {
          const next = s.appFavoriteClipTypes.includes(clipType)
            ? s.appFavoriteClipTypes.filter((n) => n !== clipType)
            : [...s.appFavoriteClipTypes, clipType]
          writeAppFavoriteClipTypes(next)
          return { appFavoriteClipTypes: next }
        }),
      toggleLogsPanel: () => set((s) => ({ showLogsPanel: !s.showLogsPanel })),
      toggleSettingsPanel: () => set((s) => ({ showSettingsPanel: !s.showSettingsPanel })),
      setSettingsPanelOpen: (open: boolean) => set({ showSettingsPanel: open }),
      setAppView: (view: AppView) => set({ appView: view }),
      setFocusedJobId: (id: string | null) => set({ focusedJobId: id }),
      openJobsView: (jobId?: string | null) =>
        set({
          appView: 'jobs',
          focusedJobId: jobId ?? null,
          isPlaying: false,
          showSettingsPanel: false,
        }),
      backToEditor: () => set({ appView: 'editor' }),
      setAppSettings: (patch: Partial<AppSettings>) =>
        set((s) => {
          const next = sanitizeAppSettings({ ...s.appSettings, ...patch })
          writeAppSettings(next)
          const localeChanged =
            patch.locale !== undefined && patch.locale !== s.appSettings.locale
          return {
            appSettings: next,
            ...(localeChanged ? { catalogDetailCache: {} } : {}),
          }
        }),
      setApiConnectionStatus: (status: ApiConnectionStatus) =>
        set({ apiConnectionStatus: status }),
      setApiRetryInSeconds: (seconds: number | null) =>
        set({ apiRetryInSeconds: seconds }),
      setComposeHealth: (health: ComposeHealth | null) => set({ composeHealth: health }),
      setPexelsAvailable: (available: boolean | null) => set({ pexelsAvailable: available }),
      setFfmpegAvailable: (available: boolean | null) => set({ ffmpegAvailable: available }),
      requestApiRetryNow: () => set((s) => ({ apiRetryNonce: s.apiRetryNonce + 1 })),
      appendEventLog: (level: EventLogEntry['level'], message: string) =>
        set((s) => ({
          eventLogs: [
            ...s.eventLogs,
            { id: newId('log'), at: Date.now(), level, message },
          ].slice(-300),
        })),
      clearEventLogs: () => set({ eventLogs: [] }),
      reconcilePluginAvailability: (availableClipTypes: string[]) => {
        const available = new Set(availableClipTypes)
        let reactivatedClips = 0
        let stillMissingClips = 0
        let reactivatedProjectSettings = 0
        let stillMissingProjectSettings = 0

        set((s) => ({
          tracks: s.tracks.map((track) => ({
            ...track,
            clips: track.clips.map((el) => {
              if (el.status !== 'missing_plugin') return el
              if (available.has(el.clip_type)) {
                reactivatedClips += 1
                const { status, ...rest } = el
                return rest
              }
              stillMissingClips += 1
              return el
            }),
          })),
          projectSettings: s.projectSettings.map((setting) => {
            if (setting.status !== 'missing_plugin') return setting
            if (available.has(setting.clip_type)) {
              reactivatedProjectSettings += 1
              const { status, ...rest } = setting
              return rest
            }
            stillMissingProjectSettings += 1
            return setting
          }),
        }))

        return {
          reactivatedClips,
          stillMissingClips,
          reactivatedProjectSettings,
          stillMissingProjectSettings,
        }
      },

      // ---- Project lifecycle ----------------------------------------------
      loadProject: ({
        meta,
        typography,
        colors,
        paletteSource,
        tracks,
        sounds,
        timelineLayout,
        projectSettings,
        importBundleId,
      }: Pick<
        ProjectState,
        | 'meta'
        | 'typography'
        | 'colors'
        | 'paletteSource'
        | 'tracks'
        | 'sounds'
        | 'timelineLayout'
        | 'projectSettings'
        | 'importBundleId'
      >) => {
        const normalizedTracks = tracks
          .filter((t) => (t.trackType ?? 'skia') !== 'audio')
          .map((t) => ({
            ...t,
            enabled: t.enabled ?? true,
            disableMode: t.disableMode ?? 'bypass_compute',
            trackType: t.trackType ?? 'skia',
            layout: (t.trackType ?? 'skia') === 'post' ? 'fill' : t.layout,
            headerFraction: t.headerFraction ?? null,
            clips: t.clips.map((el) => ({
              ...el,
              enabled: el.enabled ?? true,
            })),
          }))
          .map((t) =>
            t.trackType === 'post'
              ? { ...t, clips: t.clips.slice(0, 1) }
              : t,
          )
        const normalizedSounds = sounds.map((snd) => sanitizeSoundPatch(snd, {}))
        const normalizedProjectSettings = projectSettings.map(normalizeProjectSetting)
        const layout =
          timelineLayout.length > 0
            ? resolveTimelineLayout(timelineLayout, normalizedTracks, normalizedSounds)
            : defaultTimelineLayout(normalizedTracks, normalizedSounds)
        set((s) => ({
          meta,
          typography: cloneFontPalette(typography),
          colors: cloneJobColors(colors),
          paletteSource,
          tracks: tracksOrderFromLayout(layout, normalizedTracks),
          sounds: soundsOrderFromLayout(layout, normalizedSounds),
          timelineLayout: layout,
          projectSettings: normalizedProjectSettings,
          importBundleId: importBundleId ?? null,
          selection: null,
          pluginPicker: null,
          previewTime: 0,
          platformPresetId: null,
          prepareWarnings: [],
          appSettings: appSettingsForProjectLoad(s.appSettings),
          projectLoadEpoch: s.projectLoadEpoch + 1,
        }))
        useProjectStore.temporal.getState().clear()
        resetPrepareWarningDiagnostics()
        clearAudioBufferCache()
        clearWaveformPeaksCache()
      },

      resetProject: () => {
        set((s) => ({
          meta: { ...DEFAULT_META },
          typography: cloneFontPalette(DEFAULT_FONT_PALETTE),
          colors: cloneJobColors(DEFAULT_JOB_COLORS),
          paletteSource: { ...DEFAULT_PALETTE_SOURCE },
          tracks: [],
          sounds: [],
          timelineLayout: [],
          projectSettings: [],
          importBundleId: null,
          selection: null,
          pluginPicker: null,
          previewTime: 0,
          platformPresetId: DEFAULT_PLATFORM_PRESET_ID,
          prepareWarnings: [],
          appSettings: appSettingsForProjectLoad(s.appSettings),
          projectLoadEpoch: s.projectLoadEpoch + 1,
        }))
        useProjectStore.temporal.getState().clear()
        resetPrepareWarningDiagnostics()
        clearAudioBufferCache()
        clearWaveformPeaksCache()
      },
    }) as ProjectState,
    // Only track mutations that affect project content in undo history,
    // not ephemeral UI state like selection or theme.
    {
      limit: PROJECT_UNDO_HISTORY_LIMIT,
      partialize: (s) => ({
        meta: s.meta,
        typography: s.typography,
        colors: s.colors,
        paletteSource: s.paletteSource,
        tracks: s.tracks,
        sounds: s.sounds,
        timelineLayout: s.timelineLayout,
        projectSettings: s.projectSettings,
      }),
      equality: (pastState, currentState) =>
        projectHistorySliceEqual(pastState, currentState),
    }
  )
)

// ---------------------------------------------------------------------------
// Selectors
// ---------------------------------------------------------------------------

/** Resolve effective duration for a track (null → project duration). */
export function resolvedTrackDuration(track: Track, meta: ProjectMeta): number {
  return track.duration ?? meta.duration
}

/** Resolve effective duration for a sound (null → project duration). */
export function resolvedSoundDuration(sound: Sound, meta: ProjectMeta): number {
  return sound.duration ?? meta.duration
}

/** Resolve effective duration for a clip (null → resolved track duration). */
export function resolvedClipDuration(
  clip: Clip,
  track: Track,
  meta: ProjectMeta
): number {
  return clip.duration ?? resolvedTrackDuration(track, meta)
}

/** Serialize project state to RenderJob JSON for export / preview / API. */
export function toGraphJSON(
  state: Pick<
    ProjectState,
    'meta' | 'typography' | 'colors' | 'paletteSource' | 'tracks' | 'sounds' | 'projectSettings'
  >,
  locale?: string,
) {
  return toRenderJob({ ...state, locale })
}

export { toRenderJob } from '@/lib/renderJob'
export type { FontPalette, FontRole } from '@/lib/typography'

/** Undo last change to `meta` / `tracks` / `projectSettings`. Clears selection (simple model). */
export function projectUndo() {
  const { pastStates, undo } = useProjectStore.temporal.getState()
  if (pastStates.length === 0) return
  undo()
  useProjectStore.getState().select(null)
}

/** Redo. Clears selection (simple model). */
export function projectRedo() {
  const { futureStates, redo } = useProjectStore.temporal.getState()
  if (futureStates.length === 0) return
  redo()
  useProjectStore.getState().select(null)
}

export { newId }
