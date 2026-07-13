import { tKey } from '@/lib/i18n'
import type { TimelineDropFailure } from './types'
import { fileExtension } from './fileKind'

const IMAGE_MIME = new Set(['image/jpeg', 'image/png', 'image/webp'])
const IMAGE_EXT = new Set(['.jpg', '.jpeg', '.png', '.webp'])

const AUDIO_MIME_PREFIX = 'audio/'
const AUDIO_EXT = new Set(['.wav', '.mp3', '.flac', '.ogg', '.m4a', '.aac'])
const LOSSLESS_AUDIO_EXT = new Set(['.wav', '.flac'])
const LOSSLESS_AUDIO_MIME = new Set(['audio/wav', 'audio/x-wav', 'audio/flac'])

const VIDEO_MIME_PREFIX = 'video/'
const VIDEO_EXT = new Set(['.mp4', '.mov', '.webm', '.mkv'])

export function isTimelineGifFile(file: File): boolean {
  return file.type === 'image/gif' || fileExtension(file.name) === '.gif'
}

export function isTimelineImageFile(file: File): boolean {
  if (file.type === 'image/gif') return false
  if (file.type && IMAGE_MIME.has(file.type)) return true
  return IMAGE_EXT.has(fileExtension(file.name))
}

export function isTimelineAudioFile(file: File): boolean {
  if (file.type.startsWith(AUDIO_MIME_PREFIX)) return true
  return AUDIO_EXT.has(fileExtension(file.name))
}

export function isLosslessAudioFile(file: File): boolean {
  if (file.type && LOSSLESS_AUDIO_MIME.has(file.type)) return true
  return LOSSLESS_AUDIO_EXT.has(fileExtension(file.name))
}

export function isTimelineVideoFile(file: File): boolean {
  if (file.type.startsWith(VIDEO_MIME_PREFIX)) return true
  return VIDEO_EXT.has(fileExtension(file.name))
}

export function isTimelineProjectJsonFile(file: File): boolean {
  if (file.type === 'application/json') return true
  return fileExtension(file.name) === '.json'
}

export type TimelineFileKind = 'image' | 'video' | 'audio'

export function classifyTimelineFile(
  file: File,
): { kind: TimelineFileKind } | { kind: 'reject'; failure: TimelineDropFailure } {
  if (isTimelineGifFile(file)) {
    return {
      kind: 'reject',
      failure: { name: file.name, message: tKey('timeline_drop_gif_rejected') },
    }
  }
  if (isTimelineImageFile(file)) return { kind: 'image' }
  if (isTimelineVideoFile(file)) return { kind: 'video' }
  if (isTimelineAudioFile(file)) return { kind: 'audio' }
  return {
    kind: 'reject',
    failure: { name: file.name, message: tKey('timeline_drop_type_error') },
  }
}
