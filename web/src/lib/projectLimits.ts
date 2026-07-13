import messages from '@/lib/i18n.messages.json'
import { metaWithinRenderLimits } from '@/lib/renderLimits'
import type { ServerConfig } from '@/lib/serverConfig'
import type { ProjectMeta, Track } from '@/store/projectStore'
import type { Sound } from '@/lib/sound'

export type LimitViolationCode =
  | 'limit_tracks_exceeded'
  | 'limit_clips_per_track_exceeded'
  | 'limit_duration_exceeded'
  | 'limit_width_exceeded'
  | 'limit_height_exceeded'
  | 'limit_fps_exceeded'

export interface LimitViolation {
  code: LimitViolationCode
  max: number
  actual: number
  trackId?: string
  trackLabel?: string
}

export interface ApiLimitError {
  code: string
  max: number
  actual: number
  detail?: string
  track_index?: number
}

type LimitConfig = Pick<
  ServerConfig,
  | 'maxTracks'
  | 'maxClipsPerTrack'
  | 'maxDurationS'
  | 'maxWidth'
  | 'maxHeight'
  | 'maxFps'
>

export function timelineRowCount(tracks: Track[], sounds: Sound[]): number {
  return tracks.length + sounds.length
}

export function canAddTimelineRow(
  tracks: Track[],
  sounds: Sound[],
  config: Pick<ServerConfig, 'maxTracks'>,
): boolean {
  return timelineRowCount(tracks, sounds) < config.maxTracks
}

export function canAddClipToTrack(
  track: Track,
  config: Pick<ServerConfig, 'maxClipsPerTrack'>,
): boolean {
  if ((track.trackType ?? 'skia') === 'post') return true
  return track.clips.length < config.maxClipsPerTrack
}

function getRenderLimitViolations(meta: ProjectMeta, config: LimitConfig): LimitViolation[] {
  if (metaWithinRenderLimits(meta, config)) {
    return []
  }
  const violations: LimitViolation[] = []
  if (meta.duration > config.maxDurationS) {
    violations.push({
      code: 'limit_duration_exceeded',
      max: config.maxDurationS,
      actual: Math.ceil(meta.duration),
    })
  }
  if (meta.width > config.maxWidth) {
    violations.push({
      code: 'limit_width_exceeded',
      max: config.maxWidth,
      actual: meta.width,
    })
  }
  if (meta.height > config.maxHeight) {
    violations.push({
      code: 'limit_height_exceeded',
      max: config.maxHeight,
      actual: meta.height,
    })
  }
  if (meta.fps > config.maxFps) {
    violations.push({
      code: 'limit_fps_exceeded',
      max: config.maxFps,
      actual: Math.ceil(meta.fps),
    })
  }
  return violations
}

export function getProjectLimitViolations(
  tracks: Track[],
  sounds: Sound[],
  config: LimitConfig,
  meta?: ProjectMeta,
): LimitViolation[] {
  const violations: LimitViolation[] = meta ? getRenderLimitViolations(meta, config) : []
  const rows = timelineRowCount(tracks, sounds)
  if (rows > config.maxTracks) {
    violations.push({
      code: 'limit_tracks_exceeded',
      max: config.maxTracks,
      actual: rows,
    })
  }
  for (const track of tracks) {
    const count = track.clips.length
    if (count > config.maxClipsPerTrack) {
      violations.push({
        code: 'limit_clips_per_track_exceeded',
        max: config.maxClipsPerTrack,
        actual: count,
        trackId: track.id,
        trackLabel: track.label,
      })
    }
  }
  return violations
}

export function isOverProjectLimits(
  tracks: Track[],
  sounds: Sound[],
  config: LimitConfig,
  meta?: ProjectMeta,
): boolean {
  return getProjectLimitViolations(tracks, sounds, config, meta).length > 0
}

type LocalizedLimitKey =
  | 'limit_tracks_exceeded'
  | 'limit_clips_per_track_exceeded'
  | 'limit_duration_exceeded'
  | 'limit_width_exceeded'
  | 'limit_height_exceeded'
  | 'limit_fps_exceeded'

function localizedLimitMessage(
  key: LocalizedLimitKey,
  params: Record<string, string>,
  locale: string,
): string {
  const table = messages[locale as keyof typeof messages] as typeof messages.en | undefined
  let text = table?.[key] ?? messages.en[key]
  for (const [name, value] of Object.entries(params)) {
    text = text.replace(`{${name}}`, value)
  }
  return text
}

export function formatLimitViolation(v: LimitViolation, locale = 'en'): string {
  if (v.code === 'limit_tracks_exceeded') {
    return localizedLimitMessage('limit_tracks_exceeded', {
      max: String(v.max),
      actual: String(v.actual),
    }, locale)
  }
  if (v.code === 'limit_clips_per_track_exceeded') {
    const trackHint = v.trackLabel ? ` (${v.trackLabel})` : ''
    return localizedLimitMessage('limit_clips_per_track_exceeded', {
      max: String(v.max),
      actual: String(v.actual),
      track: trackHint,
    }, locale)
  }
  if (v.code === 'limit_duration_exceeded') {
    return localizedLimitMessage('limit_duration_exceeded', {
      max: String(v.max),
      actual: String(v.actual),
    }, locale)
  }
  if (v.code === 'limit_width_exceeded') {
    return localizedLimitMessage('limit_width_exceeded', {
      max: String(v.max),
      actual: String(v.actual),
    }, locale)
  }
  if (v.code === 'limit_height_exceeded') {
    return localizedLimitMessage('limit_height_exceeded', {
      max: String(v.max),
      actual: String(v.actual),
    }, locale)
  }
  return localizedLimitMessage('limit_fps_exceeded', {
    max: String(v.max),
    actual: String(v.actual),
  }, locale)
}

export function formatApiLimitError(error: ApiLimitError, locale = 'en'): string {
  if (error.code === 'limit_tracks_exceeded') {
    return localizedLimitMessage('limit_tracks_exceeded', {
      max: String(error.max),
      actual: String(error.actual),
    }, locale)
  }
  if (error.code === 'limit_clips_per_track_exceeded') {
    return localizedLimitMessage('limit_clips_per_track_exceeded', {
      max: String(error.max),
      actual: String(error.actual),
      track: '',
    }, locale)
  }
  if (error.code === 'limit_duration_exceeded') {
    return localizedLimitMessage('limit_duration_exceeded', {
      max: String(error.max),
      actual: String(error.actual),
    }, locale)
  }
  if (error.code === 'limit_width_exceeded') {
    return localizedLimitMessage('limit_width_exceeded', {
      max: String(error.max),
      actual: String(error.actual),
    }, locale)
  }
  if (error.code === 'limit_height_exceeded') {
    return localizedLimitMessage('limit_height_exceeded', {
      max: String(error.max),
      actual: String(error.actual),
    }, locale)
  }
  if (error.code === 'limit_fps_exceeded') {
    return localizedLimitMessage('limit_fps_exceeded', {
      max: String(error.max),
      actual: String(error.actual),
    }, locale)
  }
  return error.detail ?? error.code
}

export function previewErrorMessage(error: unknown, locale = 'en'): string {
  if (error && typeof error === 'object' && 'code' in error) {
    return formatApiLimitError(error as ApiLimitError, locale)
  }
  return typeof error === 'string' ? error : String(error)
}
