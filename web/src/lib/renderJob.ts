import type { Sound } from '@/lib/sound'
import { effectiveSoundEnabled, parseAnalyzerKind } from '@/lib/sound'
import type { TimelineLayoutEntry } from '@/lib/timelineLayout'
import { isSplitLayout, parseHeaderFraction } from '@/lib/trackVisualSettings'
import { catalogDetailCacheKey, type ClipCatalogDetail } from '@/lib/catalogDetail'
import type { Clip, ProjectSetting, ProjectMeta, Track } from '@/store/projectStore'
import {
  DEFAULT_JOB_COLORS,
  DEFAULT_PALETTE_SOURCE,
  cloneJobColors,
  parseJobColors,
  parsePaletteSource,
  type JobColorPalette,
  type PaletteSource,
} from '@/lib/jobColors'
import {
  DEFAULT_FONT_PALETTE,
  cloneFontPalette,
  mergeDefaultTypographySetting,
  type FontPalette,
  REFERENCE_HEIGHT,
} from '@/lib/typography'

export { REFERENCE_HEIGHT } from '@/lib/typography'

export interface RenderSoundJson {
  sound_type: 'std-sound'
  id: string
  bus: string
  source: string
  volume?: number
  seek?: number
  analyzer?: string
  beat_tightness?: number
  start?: number
  duration?: number | null
  enabled?: boolean
}

export type ExportQuality = 'draft' | 'standard' | 'master'

export interface RenderJobJson {
  schema_version?: number
  title?: string
  author?: string
  description?: string
  width: number
  height: number
  fps: number
  duration: number
  export_quality?: ExportQuality
  locale?: string
  reference_height?: number
  colors?: JobColorPalette
  palette_source?: PaletteSource
  typography?: FontPalette
  typography_setting?: {
    setting_type?: string
    family?: string
    mono_family?: string
    enabled?: boolean
  }
  tracks?: RenderTrackJson[]
  sounds?: RenderSoundJson[]
}

/** Web project file — RenderJob fields plus editor-only layout. */
export interface WebProjectJson extends RenderJobJson {
  timeline_layout?: TimelineLayoutEntry[]
}

interface RenderTrackJson {
  clip_type: string
  id: string
  start?: number
  duration?: number | null
  enabled?: boolean
  disable_mode?: string
  layout?: { type: string; header_fraction?: number }
  transition_in?: unknown
  transition_out?: unknown
  effects?: Record<string, unknown>[]
  clips?: RenderClipJson[]
}

type RenderClipJson = Record<string, unknown> & {
  clip_type: string
  id: string
  start?: number
  duration?: number | null
  enabled?: boolean
}

const TRACK_TYPE_MAP: Record<Exclude<Track['trackType'], 'audio' | undefined> & string, string> = {
  skia: 'std-skia-track',
  gl: 'std-gl-track',
  post: 'std-post-track',
}

const TRACK_TYPE_REVERSE: Record<string, Track['trackType']> = {
  'std-skia-track': 'skia',
  'std-gl-track': 'gl',
  'std-post-track': 'post',
}

const CLIP_EXPORT_KEYS = new Set([
  'clip_type',
  'id',
  'start',
  'duration',
  'enabled',
  'effects',
])

const EFFECT_EXPORT_KEYS = new Set(['effect_type', 'id', 'enabled'])

function trackLayoutToJson(track: Track): RenderTrackJson['layout'] {
  if (!isSplitLayout(track.layout)) {
    return { type: track.layout }
  }
  const layout: NonNullable<RenderTrackJson['layout']> = { type: track.layout }
  if (track.headerFraction != null) {
    layout.header_fraction = track.headerFraction
  }
  return layout
}

function trackClipType(track: Track): string {
  const type = track.trackType ?? 'skia'
  if (type === 'audio') return 'std-skia-track'
  return TRACK_TYPE_MAP[type as keyof typeof TRACK_TYPE_MAP] ?? 'std-skia-track'
}

export function clipToJson(
  clip: Clip,
  schemaDefaults?: Record<string, unknown>,
): RenderClipJson {
  const params = { ...(schemaDefaults ?? {}), ...clip.params }
  if ('role' in params && !('typography_role' in params)) {
    params.typography_role = params.role
    delete params.role
  }
  for (const key of CLIP_EXPORT_KEYS) {
    delete params[key]
  }
  const json: RenderClipJson = {
    ...params,
    clip_type: clip.clip_type,
    id: clip.id,
    start: clip.start,
    duration: clip.duration,
    enabled: clip.enabled ?? true,
  }
  const effects = clip.effects ?? []
  if (effects.length > 0) {
    json.effects = effects.map((fx) => effectToJson(fx))
  }
  return json
}
function effectToJson(fx: import('@/store/projectStore').EffectInstance): Record<string, unknown> {
  const fxParams = { ...fx.params }
  for (const key of EFFECT_EXPORT_KEYS) {
    delete fxParams[key]
  }
  return {
    ...fxParams,
    effect_type: fx.effect_type,
    id: fx.id,
    enabled: fx.enabled ?? true,
  }
}

function effectFromJson(raw: Record<string, unknown>): import('@/store/projectStore').EffectInstance {
  const { effect_type, id, enabled, effects: _e, ...rest } = raw
  return {
    id: String(id ?? ''),
    effect_type: String(effect_type ?? ''),
    label: String(effect_type ?? ''),
    enabled: enabled !== false,
    params: rest,
  }
}

function clipFromJson(raw: RenderClipJson, trackStart: number): Clip {
  const { clip_type, id, start, duration, enabled, effects: rawEffects, ...rest } = raw
  const params = { ...rest }
  if ('role' in params && !('typography_role' in params)) {
    params.typography_role = params.role
    delete params.role
  }
  const relStart =
    typeof start === 'number' ? (start >= trackStart ? start - trackStart : start) : 0
  const effects =
    Array.isArray(rawEffects) && rawEffects.length > 0
      ? rawEffects.map((fx) => effectFromJson(fx as Record<string, unknown>))
      : undefined
  return {
    id: String(id),
    clip_type: String(clip_type),
    label: String(clip_type),
    start: relStart,
    duration: typeof duration === 'number' ? duration : null,
    enabled: enabled !== false,
    params,
    ...(effects ? { effects } : {}),
  }
}

function soundToJson(sound: Sound): RenderSoundJson {
  return {
    sound_type: 'std-sound',
    id: sound.id,
    bus: sound.bus.trim(),
    source: sound.source,
    volume: sound.volume,
    seek: sound.seek,
    analyzer: sound.analyzer,
    beat_tightness: sound.beat_tightness,
    start: sound.start,
    duration: sound.duration,
    enabled: effectiveSoundEnabled(sound),
  }
}

function soundFromJson(raw: Record<string, unknown>): Sound {
  return {
    id: String(raw.id ?? ''),
    bus: typeof raw.bus === 'string' ? raw.bus : '',
    source: typeof raw.source === 'string' ? raw.source : '',
    volume: typeof raw.volume === 'number' ? raw.volume : 1,
    seek: typeof raw.seek === 'number' ? raw.seek : 0,
    analyzer: parseAnalyzerKind(raw.analyzer),
    beat_tightness: typeof raw.beat_tightness === 'number' ? raw.beat_tightness : 200,
    start: typeof raw.start === 'number' ? raw.start : 0,
    duration: typeof raw.duration === 'number' ? raw.duration : null,
    enabled: raw.enabled !== false,
  }
}

export function toRenderJob(state: {
  meta: ProjectMeta
  tracks: Track[]
  sounds: Sound[]
  projectSettings: ProjectSetting[]
  typography: FontPalette
  colors: JobColorPalette
  paletteSource: PaletteSource
  locale?: string
  description?: string
  catalogDetailCache?: Record<string, ClipCatalogDetail>
}): RenderJobJson {
  const { meta, tracks, sounds, typography, colors, paletteSource, locale = 'en' } = state
  const detailCache = state.catalogDetailCache
  const compositorTracks = tracks.filter((t) => (t.trackType ?? 'skia') !== 'audio')
  return {
    schema_version: 1,
    title: meta.title.trim() || 'Untitled',
    author: meta.author.trim(),
    description: state.description ?? '',
    width: meta.width,
    height: meta.height,
    fps: meta.fps,
    duration: meta.duration,
    export_quality: meta.exportQuality,
    locale,
    reference_height: REFERENCE_HEIGHT,
    colors: cloneJobColors(colors),
    palette_source: paletteSource,
    typography: cloneFontPalette(typography),
    tracks: compositorTracks.map((track) => {
      const isPostTrack = (track.trackType ?? 'skia') === 'post'
      const trackEffects = !isPostTrack ? (track.effects ?? []) : []
      return {
        clip_type: trackClipType(track),
        id: track.id,
        start: track.start,
        duration: track.duration,
        enabled: track.enabled,
        disable_mode: track.disableMode,
        ...(isPostTrack ? {} : { layout: trackLayoutToJson(track) }),
        transition_in: track.transition_in ?? null,
        transition_out: track.transition_out ?? null,
        ...(trackEffects.length > 0
          ? { effects: trackEffects.map((fx) => effectToJson(fx)) }
          : {}),
        clips: (isPostTrack ? track.clips.slice(0, 1) : track.clips).map((clip) =>
          clipToJson(
            clip,
            detailCache?.[catalogDetailCacheKey(clip.clip_type, locale)]?.defaults,
          ),
        ),
      }
    }),
    sounds: sounds.map(soundToJson),
  }
}

export function toWebProjectJson(state: {
  meta: ProjectMeta
  tracks: Track[]
  sounds: Sound[]
  timelineLayout: TimelineLayoutEntry[]
  projectSettings: ProjectSetting[]
  typography: FontPalette
  colors: JobColorPalette
  paletteSource: PaletteSource
  locale?: string
  description?: string
}): WebProjectJson {
  return {
    ...toRenderJob(state),
    timeline_layout: state.timelineLayout,
  }
}

export function fromRenderJob(data: RenderJobJson): {
  meta: ProjectMeta
  tracks: Track[]
  sounds: Sound[]
  typography: FontPalette
  colors: JobColorPalette
  paletteSource: PaletteSource
} {
  // Project JSON stores reference-scale typography (same as the editor store).
  // RenderJob scales by height/reference_height at render time — do not unscale here.
  let typography = data.typography
    ? cloneFontPalette(data.typography)
    : cloneFontPalette(DEFAULT_FONT_PALETTE)

  if (data.typography_setting?.setting_type === 'std-default-typography') {
    typography = mergeDefaultTypographySetting(typography, data.typography_setting)
  }

  const colors = parseJobColors(data.colors) ?? cloneJobColors(DEFAULT_JOB_COLORS)
  const paletteSource =
    parsePaletteSource(data.palette_source) ??
    (parseJobColors(data.colors) ? { type: 'custom' as const } : { ...DEFAULT_PALETTE_SOURCE })

  const tracks: Track[] = (data.tracks ?? [])
    .filter(
      (raw) =>
        TRACK_TYPE_REVERSE[raw.clip_type] !== 'audio' && raw.clip_type !== 'std-audio-track',
    )
    .map((raw) => {
      const trackStart = typeof raw.start === 'number' ? raw.start : 0
      const trackType = TRACK_TYPE_REVERSE[raw.clip_type] ?? 'skia'
      const isPostTrack = trackType === 'post'
      const rawTrackEffects = !isPostTrack ? raw.effects : undefined
      const trackEffects =
        Array.isArray(rawTrackEffects) && rawTrackEffects.length > 0
          ? rawTrackEffects.map((fx) => effectFromJson(fx as Record<string, unknown>))
          : undefined
      return {
        id: String(raw.id),
        label: String(raw.id),
        enabled: raw.enabled ?? true,
        disableMode:
          raw.disable_mode === 'mute_output' ? 'mute_output' : 'bypass_compute',
        start: trackStart,
        duration: typeof raw.duration === 'number' ? raw.duration : null,
        layout:
          isPostTrack
            ? 'fill'
            : raw.layout?.type === 'vertical' || raw.layout?.type === 'horizontal'
              ? raw.layout.type
              : 'fill',
        headerFraction: parseHeaderFraction(raw.layout?.header_fraction),
        trackType,
        transition_in: raw.transition_in as Track['transition_in'],
        transition_out: raw.transition_out as Track['transition_out'],
        ...(trackEffects ? { effects: trackEffects } : {}),
        clips: (isPostTrack ? (raw.clips ?? []).slice(0, 1) : raw.clips ?? []).map((clip) =>
          clipFromJson(clip as RenderClipJson, trackStart),
        ),
      }
    })

  const sounds: Sound[] = (data.sounds ?? []).map((raw) =>
    soundFromJson(raw as unknown as Record<string, unknown>),
  )

  return {
    meta: {
      title: typeof data.title === 'string' && data.title.trim() ? data.title.trim() : 'Untitled',
      author: typeof data.author === 'string' ? data.author : '',
      fps: data.fps ?? 24,
      duration: data.duration ?? 10,
      width: data.width ?? 1280,
      height: data.height ?? 720,
      exportQuality:
        data.export_quality === 'draft' ||
        data.export_quality === 'standard' ||
        data.export_quality === 'master'
          ? data.export_quality
          : 'master',
    },
    tracks,
    sounds,
    typography,
    colors,
    paletteSource,
  }
}

function normalizeTimelineLayout(raw: unknown): TimelineLayoutEntry[] {
  if (!Array.isArray(raw)) return []
  const out: TimelineLayoutEntry[] = []
  for (const entry of raw) {
    if (typeof entry !== 'object' || entry === null) continue
    const kind = (entry as { kind?: unknown }).kind
    const id = (entry as { id?: unknown }).id
    if ((kind === 'track' || kind === 'sound') && typeof id === 'string') {
      out.push({ kind, id })
    }
  }
  return out
}

export function fromWebProjectJson(data: WebProjectJson): ReturnType<typeof fromRenderJob> & {
  timelineLayout: TimelineLayoutEntry[]
} {
  const base = fromRenderJob(data)
  return {
    ...base,
    timelineLayout: normalizeTimelineLayout(data.timeline_layout),
  }
}

/** @deprecated Use {@link toRenderJob} for API / preview. */
export function toGraphJSON(state: {
  meta: ProjectMeta
  tracks: Track[]
  sounds: Sound[]
  projectSettings: ProjectSetting[]
  typography: FontPalette
  colors: JobColorPalette
  paletteSource: PaletteSource
  locale?: string
}) {
  return toRenderJob(state)
}
