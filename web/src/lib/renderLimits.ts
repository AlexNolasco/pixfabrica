import {
  getPlatformPreset,
  PLATFORM_PRESETS,
  type PlatformPreset,
  type PlatformPresetId,
} from '@/lib/platformPresets'
import type { ServerConfig } from '@/lib/serverConfig'
import type { ProjectMeta } from '@/store/projectStore'

export const HF_STRICT_HOST_MAX_WIDTH = 960
export const HF_STRICT_HOST_MAX_HEIGHT = 540
export const HF_DEFAULT_PLATFORM_ID: PlatformPresetId = 'video_brochure'

export type RenderLimitFields = Pick<
  ServerConfig,
  'maxDurationS' | 'maxWidth' | 'maxHeight' | 'maxFps'
>

export function isStrictRenderHost(config: RenderLimitFields): boolean {
  return config.maxWidth <= HF_STRICT_HOST_MAX_WIDTH
    && config.maxHeight <= HF_STRICT_HOST_MAX_HEIGHT
}

export function platformFitsRenderLimits(
  preset: PlatformPreset,
  config: RenderLimitFields,
): boolean {
  return preset.width <= config.maxWidth
    && preset.height <= config.maxHeight
    && preset.fps <= config.maxFps
}

export function filterPlatformPresets(config: RenderLimitFields): PlatformPreset[] {
  return PLATFORM_PRESETS.filter((preset) => platformFitsRenderLimits(preset, config))
}

export function metaWithinRenderLimits(
  meta: Pick<ProjectMeta, 'duration' | 'width' | 'height' | 'fps'>,
  config: RenderLimitFields,
): boolean {
  return meta.duration <= config.maxDurationS
    && meta.width <= config.maxWidth
    && meta.height <= config.maxHeight
    && meta.fps <= config.maxFps
}

export function resolutionFitsRenderLimits(
  width: number,
  height: number,
  config: RenderLimitFields,
): boolean {
  return width <= config.maxWidth && height <= config.maxHeight
}

export function clampMetaToRenderLimits(
  meta: ProjectMeta,
  config: RenderLimitFields,
): ProjectMeta {
  return {
    ...meta,
    duration: Math.min(meta.duration, config.maxDurationS),
    width: Math.min(meta.width, config.maxWidth),
    height: Math.min(meta.height, config.maxHeight),
    fps: Math.min(meta.fps, config.maxFps),
  }
}

function applyPlatformToMeta(
  meta: ProjectMeta,
  preset: PlatformPreset,
  config: RenderLimitFields,
): ProjectMeta {
  return {
    ...meta,
    width: preset.width,
    height: preset.height,
    fps: preset.fps,
    duration: Math.min(
      meta.duration > preset.maxSec ? preset.maxSec : meta.duration,
      config.maxDurationS,
    ),
  }
}

/** After GET /config — fit project meta to server caps without squashing aspect ratio when possible. */
export function reconcileMetaWithRenderLimits(
  meta: ProjectMeta,
  platformPresetId: PlatformPresetId | null,
  config: RenderLimitFields,
): { meta: ProjectMeta; platformPresetId: PlatformPresetId | null } {
  if (metaWithinRenderLimits(meta, config)) {
    return { meta, platformPresetId }
  }

  if (platformPresetId) {
    const preset = getPlatformPreset(platformPresetId)
    if (preset && platformFitsRenderLimits(preset, config)) {
      return {
        meta: applyPlatformToMeta(meta, preset, config),
        platformPresetId,
      }
    }
  }

  const fallbackId = isStrictRenderHost(config) ? HF_DEFAULT_PLATFORM_ID : null
  if (fallbackId) {
    const fallback = getPlatformPreset(fallbackId)
    if (fallback && platformFitsRenderLimits(fallback, config)) {
      return {
        meta: applyPlatformToMeta(meta, fallback, config),
        platformPresetId: fallbackId,
      }
    }
  }

  for (const preset of filterPlatformPresets(config)) {
    return {
      meta: applyPlatformToMeta(meta, preset, config),
      platformPresetId: preset.id,
    }
  }

  return {
    meta: clampMetaToRenderLimits(meta, config),
    platformPresetId: null,
  }
}
