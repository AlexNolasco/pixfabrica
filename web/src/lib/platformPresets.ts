import type { TranslationKey } from '@/lib/i18n'

export type PlatformPresetId =
  | 'youtube_shorts'
  | 'tiktok'
  | 'suno_ai'
  | 'bandlab_vertical'
  | 'bandlab_square'
  | 'civitai_portrait'
  | 'civitai_landscape'
  | 'discord_free'
  | 'instagram_reels'
  | 'x_twitter_landscape'
  | 'x_twitter_vertical'
  | 'video_brochure'

export type PlatformPresetGroup =
  | 'social_vertical'
  | 'social_landscape'
  | 'music'
  | 'ai_gen'
  | 'web'

export interface PlatformPreset {
  id: PlatformPresetId
  group: PlatformPresetGroup
  labelKey: TranslationKey
  width: number
  height: number
  fps: number
  maxSec: number
}

export const DEFAULT_PLATFORM_PRESET_ID: PlatformPresetId = 'youtube_shorts'

export const PLATFORM_PRESETS: PlatformPreset[] = [
  {
    id: 'youtube_shorts',
    group: 'social_vertical',
    labelKey: 'platform_youtube_shorts',
    width: 1080,
    height: 1920,
    fps: 30,
    maxSec: 60,
  },
  {
    id: 'tiktok',
    group: 'social_vertical',
    labelKey: 'platform_tiktok',
    width: 1080,
    height: 1920,
    fps: 30,
    maxSec: 600,
  },
  {
    id: 'instagram_reels',
    group: 'social_vertical',
    labelKey: 'platform_instagram_reels',
    width: 1080,
    height: 1920,
    fps: 30,
    maxSec: 90,
  },
  {
    id: 'x_twitter_vertical',
    group: 'social_vertical',
    labelKey: 'platform_x_twitter_vertical',
    width: 1080,
    height: 1920,
    fps: 30,
    maxSec: 140,
  },
  {
    id: 'x_twitter_landscape',
    group: 'social_landscape',
    labelKey: 'platform_x_twitter_landscape',
    width: 1280,
    height: 720,
    fps: 30,
    maxSec: 140,
  },
  {
    id: 'discord_free',
    group: 'social_landscape',
    labelKey: 'platform_discord_free',
    width: 1280,
    height: 720,
    fps: 30,
    maxSec: 30,
  },
  {
    id: 'suno_ai',
    group: 'music',
    labelKey: 'platform_suno_ai',
    width: 1080,
    height: 1920,
    fps: 30,
    maxSec: 240,
  },
  {
    id: 'bandlab_vertical',
    group: 'music',
    labelKey: 'platform_bandlab_vertical',
    width: 1080,
    height: 1920,
    fps: 30,
    maxSec: 180,
  },
  {
    id: 'bandlab_square',
    group: 'music',
    labelKey: 'platform_bandlab_square',
    width: 1080,
    height: 1080,
    fps: 30,
    maxSec: 180,
  },
  {
    id: 'civitai_portrait',
    group: 'ai_gen',
    labelKey: 'platform_civitai_portrait',
    width: 576,
    height: 1024,
    fps: 15,
    maxSec: 10,
  },
  {
    id: 'civitai_landscape',
    group: 'ai_gen',
    labelKey: 'platform_civitai_landscape',
    width: 1024,
    height: 576,
    fps: 15,
    maxSec: 10,
  },
  {
    id: 'video_brochure',
    group: 'web',
    labelKey: 'platform_video_brochure',
    width: 800,
    height: 480,
    fps: 30,
    maxSec: 60,
  },
]

export const PLATFORM_GROUP_ORDER: PlatformPresetGroup[] = [
  'social_vertical',
  'social_landscape',
  'music',
  'ai_gen',
  'web',
]

export const PLATFORM_GROUP_LABEL_KEYS: Record<PlatformPresetGroup, TranslationKey> = {
  social_vertical: 'optgroup_platform_social_vertical',
  social_landscape: 'optgroup_platform_social_landscape',
  music: 'optgroup_platform_music',
  ai_gen: 'optgroup_platform_ai_gen',
  web: 'optgroup_platform_web',
}

export function getPlatformPreset(id: PlatformPresetId): PlatformPreset | undefined {
  return PLATFORM_PRESETS.find((p) => p.id === id)
}
