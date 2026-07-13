import { getClipPreviewAudioOptions } from '@/lib/clipPreviewAudio'
import { catalogDetailCacheKey } from '@/lib/catalogDetail'
import { clipToJson } from '@/lib/renderJob'
import { cloneFontPalette, REFERENCE_HEIGHT } from '@/lib/typography'
import { cloneJobColors } from '@/lib/jobColors'
import type { Clip, ProjectMeta, Track } from '@/store/projectStore'
import { useProjectStore } from '@/store/projectStore'
import type { FontPalette } from '@/lib/typography'
import type { JobColorPalette } from '@/lib/jobColors'

export interface ClipPreviewMessage {
  clip: ReturnType<typeof clipToJson>
  track_kind: 'skia' | 'gl'
  colors: JobColorPalette
  typography: FontPalette
  locale: string
  fps: number
  width: number
  height: number
  reference_height: number
  t: number
  loop_seconds: number
  title?: string
  author?: string
  preview_sample?: string | null
  preview_bus_muted?: boolean
}

export function buildClipPreviewMessage(input: {
  meta: ProjectMeta
  track: Track
  clip: Clip
  colors: JobColorPalette
  typography: FontPalette
  locale: string
  t: number
  loopSeconds: number
}): ClipPreviewMessage {
  const trackType = input.track.trackType ?? 'skia'
  const trackKind = trackType === 'gl' ? 'gl' : 'skia'
  const cacheKey = catalogDetailCacheKey(input.clip.clip_type, input.locale)
  const schemaDefaults = useProjectStore.getState().catalogDetailCache[cacheKey]?.defaults
  const merged: Clip = schemaDefaults
    ? { ...input.clip, params: { ...schemaDefaults, ...input.clip.params } }
    : input.clip
  const audioOpts = getClipPreviewAudioOptions()
  const clipJson = clipToJson(merged)
  return {
    clip: clipJson,
    track_kind: trackKind,
    colors: cloneJobColors(input.colors),
    typography: cloneFontPalette(input.typography),
    locale: input.locale,
    fps: input.meta.fps,
    width: input.meta.width,
    height: input.meta.height,
    reference_height: REFERENCE_HEIGHT,
    t: input.t,
    loop_seconds: input.loopSeconds,
    title: input.meta.title.trim() || 'Untitled',
    author: input.meta.author.trim(),
    preview_sample: audioOpts.sampleId,
    preview_bus_muted: audioOpts.busMuted,
  }
}
