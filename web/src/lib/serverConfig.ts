/** Fallback policy limits — must match `pixfabrica_api.server_config` defaults. */

/** Bootstrap only — must match `pixfabrica_core.preview_dims.DEFAULT_MAX_PREVIEW_LONG_SIDE`. */
export const FALLBACK_MAX_PREVIEW_LONG_SIDE = 480
export const FALLBACK_MAX_TRACKS = 16
export const FALLBACK_MAX_CLIPS_PER_TRACK = 8
export const FALLBACK_MAX_DURATION_S = 600
export const FALLBACK_MAX_WIDTH = 1920
export const FALLBACK_MAX_HEIGHT = 1080
export const FALLBACK_MAX_FPS = 30
export const FALLBACK_DEFAULT_LOCALE = 'en' as const

const SUPPORTED_UI_LOCALES = ['en', 'es', 'zh-CN', 'ja'] as const
export type SupportedUiLocale = (typeof SUPPORTED_UI_LOCALES)[number]

/** Must match `pixfabrica_api.pexels_settings._DEFAULT_QUERIES`. */
export const FALLBACK_PEXELS_DEFAULT_QUERIES = ['inspirational', 'music'] as const

/** Must match `pixfabrica_api.pexels_settings._DEFAULT_VIDEO_QUERIES`. */
export const FALLBACK_PEXELS_DEFAULT_VIDEO_QUERIES = ['cinematic', 'abstract', 'motion'] as const

/** Must match `pixfabrica_core.media_upload.MEDIA_UPLOAD_LIMITS`. */
export const FALLBACK_UPLOAD_LIMITS = {
  audio: 10 * 1024 * 1024,
  audio_lossless: 60 * 1024 * 1024,
  image: 10 * 1024 * 1024,
  lyrics: 5 * 1024 * 1024,
  video: 15 * 1024 * 1024,
  mesh: 10 * 1024 * 1024,
  default: 16 * 1024 * 1024,
} as const

export type MediaUploadKind = keyof typeof FALLBACK_UPLOAD_LIMITS

export interface ServerConfigPayload {
  max_preview_long_side: number
  max_duration_s: number
  max_width: number
  max_height: number
  max_fps: number
  max_tracks: number
  max_clips_per_track: number
  upload_limits: Record<string, number>
  capabilities?: {
    gl_available?: boolean
    gl_reason?: string | null
    gl_renderer?: string | null
  }
  pexels_default_queries?: string[]
  pexels_default_video_queries?: string[]
  catalog?: {
    excluded_licenses?: string[]
  }
  default_locale?: string
}

export interface ServerConfig {
  maxPreviewLongSide: number
  maxDurationS: number
  maxWidth: number
  maxHeight: number
  maxFps: number
  maxTracks: number
  maxClipsPerTrack: number
  uploadLimits: Record<string, number>
  glAvailable: boolean
  glReason: string | null
  glRenderer: string | null
  pexelsDefaultQueries: string[]
  pexelsDefaultVideoQueries: string[]
  catalogExcludedLicenses: string[]
  defaultLocale: SupportedUiLocale
  /** True after a successful GET /config; false while using fallbacks only. */
  confirmed: boolean
}

function clampInt(n: unknown, min: number, fallback: number): number {
  const v = typeof n === 'number' && Number.isFinite(n) ? Math.floor(n) : fallback
  return Math.max(min, v)
}

function parsePexelsDefaultQueries(raw: unknown): string[] {
  if (!Array.isArray(raw)) return [...FALLBACK_PEXELS_DEFAULT_QUERIES]
  const queries = raw
    .filter((q): q is string => typeof q === 'string' && q.trim().length > 0)
    .map((q) => q.trim())
  return queries.length > 0 ? queries : [...FALLBACK_PEXELS_DEFAULT_QUERIES]
}

function parsePexelsDefaultVideoQueries(raw: unknown): string[] {
  if (!Array.isArray(raw)) return [...FALLBACK_PEXELS_DEFAULT_VIDEO_QUERIES]
  const queries = raw
    .filter((q): q is string => typeof q === 'string' && q.trim().length > 0)
    .map((q) => q.trim())
  return queries.length > 0 ? queries : [...FALLBACK_PEXELS_DEFAULT_VIDEO_QUERIES]
}

function parseDefaultLocale(raw: unknown): SupportedUiLocale {
  if (
    typeof raw === 'string' &&
    (SUPPORTED_UI_LOCALES as readonly string[]).includes(raw)
  ) {
    return raw as SupportedUiLocale
  }
  return FALLBACK_DEFAULT_LOCALE
}

export function fallbackServerConfig(): ServerConfig {
  return {
    maxPreviewLongSide: FALLBACK_MAX_PREVIEW_LONG_SIDE,
    maxDurationS: FALLBACK_MAX_DURATION_S,
    maxWidth: FALLBACK_MAX_WIDTH,
    maxHeight: FALLBACK_MAX_HEIGHT,
    maxFps: FALLBACK_MAX_FPS,
    maxTracks: FALLBACK_MAX_TRACKS,
    maxClipsPerTrack: FALLBACK_MAX_CLIPS_PER_TRACK,
    uploadLimits: { ...FALLBACK_UPLOAD_LIMITS },
    glAvailable: true,
    glReason: null,
    glRenderer: null,
    pexelsDefaultQueries: [...FALLBACK_PEXELS_DEFAULT_QUERIES],
    pexelsDefaultVideoQueries: [...FALLBACK_PEXELS_DEFAULT_VIDEO_QUERIES],
    catalogExcludedLicenses: [],
    defaultLocale: FALLBACK_DEFAULT_LOCALE,
    confirmed: false,
  }
}

export function uploadMaxBytes(
  kind: string,
  config: Pick<ServerConfig, 'uploadLimits'>,
): number {
  const key = kind in FALLBACK_UPLOAD_LIMITS ? kind : 'default'
  const fromServer = config.uploadLimits[key] ?? config.uploadLimits.default
  if (typeof fromServer === 'number' && fromServer > 0) return fromServer
  return FALLBACK_UPLOAD_LIMITS[key as MediaUploadKind]
}

export function parseServerConfigPayload(payload: ServerConfigPayload): ServerConfig {
  const uploadLimits: Record<string, number> = {}
  if (payload.upload_limits && typeof payload.upload_limits === 'object') {
    for (const [kind, bytes] of Object.entries(payload.upload_limits)) {
      if (typeof bytes === 'number' && Number.isFinite(bytes) && bytes > 0) {
        uploadLimits[kind] = Math.floor(bytes)
      }
    }
  }
  return {
    maxPreviewLongSide: clampInt(
      payload.max_preview_long_side,
      1,
      FALLBACK_MAX_PREVIEW_LONG_SIDE,
    ),
    maxDurationS: clampInt(payload.max_duration_s, 1, FALLBACK_MAX_DURATION_S),
    maxWidth: clampInt(payload.max_width, 1, FALLBACK_MAX_WIDTH),
    maxHeight: clampInt(payload.max_height, 1, FALLBACK_MAX_HEIGHT),
    maxFps: clampInt(payload.max_fps, 1, FALLBACK_MAX_FPS),
    maxTracks: clampInt(payload.max_tracks, 1, FALLBACK_MAX_TRACKS),
    maxClipsPerTrack: clampInt(payload.max_clips_per_track, 1, FALLBACK_MAX_CLIPS_PER_TRACK),
    uploadLimits,
    glAvailable: payload.capabilities?.gl_available !== false,
    glReason:
      typeof payload.capabilities?.gl_reason === 'string'
        ? payload.capabilities.gl_reason
        : null,
    glRenderer:
      typeof payload.capabilities?.gl_renderer === 'string'
        ? payload.capabilities.gl_renderer
        : null,
    pexelsDefaultQueries: parsePexelsDefaultQueries(payload.pexels_default_queries),
    pexelsDefaultVideoQueries: parsePexelsDefaultVideoQueries(payload.pexels_default_video_queries),
    catalogExcludedLicenses: Array.isArray(payload.catalog?.excluded_licenses)
      ? payload.catalog.excluded_licenses.filter(
          (value): value is string => typeof value === 'string' && value.trim().length > 0,
        )
      : [],
    defaultLocale: parseDefaultLocale(payload.default_locale),
    confirmed: true,
  }
}
