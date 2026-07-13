import { prefetchAudioBuffer } from '@/lib/audioBufferCache'
import { apiUploadMedia, formatMaxBytes } from '@/lib/mediaUpload'
import { tKey } from '@/lib/i18n'
import { uploadMaxBytes } from '@/lib/serverConfig'
import { useProjectStore } from '@/store/projectStore'
import { buildAudioDropItem, uniqueBusName } from './audioDrop'
import { classifyTimelineFile, isLosslessAudioFile } from './classify'
import { fileStem } from './fileStem'
import { buildImageDropItem } from './imageDrop'
import type {
  TimelineDropFailure,
  TimelineDropResult,
  TimelineImportBatch,
} from './types'
import { buildVideoDropItem } from './videoDrop'

function seedTakenBusNames(): Set<string> {
  const taken = new Set<string>()
  for (const s of useProjectStore.getState().sounds) {
    const name = s.bus.trim()
    if (name) taken.add(name)
  }
  return taken
}

export async function runTimelineImport(
  files: File[],
  onProgress: (current: number, total: number, kind?: 'image' | 'video' | 'audio') => void,
): Promise<TimelineDropResult> {
  const failed: TimelineDropFailure[] = []
  const work: Array<{ file: File; kind: 'image' | 'video' | 'audio' }> = []

  for (const file of files) {
    const classified = classifyTimelineFile(file)
    if (classified.kind === 'reject') {
      failed.push(classified.failure)
      continue
    }
    work.push({ file, kind: classified.kind })
  }

  if (work.length === 0) {
    return { succeeded: 0, failed }
  }

  const batch: TimelineImportBatch = {
    visualTracks: [],
    sounds: [],
    layoutOrder: [],
  }
  const takenBusNames = seedTakenBusNames()
  const total = work.length
  const serverConfig = useProjectStore.getState().serverConfig

  for (let i = 0; i < work.length; i++) {
    const { file, kind } = work[i]!
    onProgress(i + 1, total, kind)
    try {
      if (kind === 'image') {
        if (file.size > uploadMaxBytes('image', serverConfig)) {
          failed.push({
            name: file.name,
            message: tKey('timeline_drop_image_too_large').replace(
              '{max}',
              formatMaxBytes(uploadMaxBytes('image', serverConfig)),
            ),
          })
          continue
        }
        const item = await buildImageDropItem(file, fileStem(file.name))
        batch.layoutOrder.push({ kind: 'track', trackIndex: batch.visualTracks.length })
        batch.visualTracks.push(item)
      } else if (kind === 'video') {
        if (file.size > uploadMaxBytes('video', serverConfig)) {
          failed.push({
            name: file.name,
            message: tKey('timeline_drop_video_too_large').replace(
              '{max}',
              formatMaxBytes(uploadMaxBytes('video', serverConfig)),
            ),
          })
          continue
        }
        const item = await buildVideoDropItem(file, fileStem(file.name))
        batch.layoutOrder.push({ kind: 'track', trackIndex: batch.visualTracks.length })
        batch.visualTracks.push(item)
      } else {
        const audioLimitKind = isLosslessAudioFile(file) ? 'audio_lossless' : 'audio'
        const audioMaxBytes = uploadMaxBytes(audioLimitKind, serverConfig)
        if (file.size > audioMaxBytes) {
          failed.push({
            name: file.name,
            message: tKey('timeline_drop_audio_too_large').replace(
              '{max}',
              formatMaxBytes(audioMaxBytes),
            ),
          })
          continue
        }
        const bus = uniqueBusName(fileStem(file.name), takenBusNames)
        const uploaded = await apiUploadMedia(file, 'audio')
        const item = buildAudioDropItem(bus, uploaded.path)
        prefetchAudioBuffer(uploaded.path)
        batch.layoutOrder.push({ kind: 'sound', soundIndex: batch.sounds.length })
        batch.sounds.push(item)
      }
    } catch (exc) {
      failed.push({
        name: file.name,
        message: exc instanceof Error ? exc.message : tKey('timeline_drop_failed'),
      })
    }
  }

  const succeeded = batch.visualTracks.length + batch.sounds.length
  if (succeeded === 0) {
    return { succeeded: 0, failed }
  }

  const placed = useProjectStore.getState().applyTimelineImportBatch(batch)
  if (failed.length > 0) {
    useProjectStore.getState().appendEventLog(
      'warn',
      tKey('timeline_drop_partial_summary')
        .replace('{ok}', String(succeeded))
        .replace('{failed}', failed.map((f) => f.name).join(', ')),
    )
  }

  return {
    succeeded,
    failed,
    frontTrackId: placed?.frontTrackId,
    frontClipId: placed?.frontClipId,
    frontSoundId: placed?.frontSoundId,
  }
}
