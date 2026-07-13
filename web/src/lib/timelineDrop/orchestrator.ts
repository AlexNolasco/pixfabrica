import type { TranslationKey } from '@/lib/i18n'
import { tKey } from '@/lib/i18n'
import { prepareTimelineImport } from '@/lib/previewTransport'
import {
  parseProjectImportFile,
  type ProjectImportPayload,
} from '@/lib/projectFileActions'
import { useProjectStore } from '@/store/projectStore'
import { isTimelineProjectJsonFile } from './classify'
import { runTimelineImport } from './runImport'
import type { TimelineDropResult } from './types'

export function dragEventHasFiles(dt: DataTransfer): boolean {
  return [...dt.types].includes('Files')
}

export type TimelineDropRejectReason =
  | 'playing'
  | 'api_offline'
  | 'no_files'
  | 'preview_stop_timeout'
  | null

export type TimelineProjectJsonDropResult =
  | { kind: 'playing' }
  | { kind: 'preview_stop_timeout' }
  | { kind: 'invalid'; filename: string; messageKey: TranslationKey }
  | { kind: 'ready'; payload: ProjectImportPayload; filename: string }

export function firstProjectJsonFile(files: File[]): File | undefined {
  return files.find(isTimelineProjectJsonFile)
}

export function timelineDropGuard(): TimelineDropRejectReason {
  const state = useProjectStore.getState()
  if (state.isPlaying) return 'playing'
  if (state.apiConnectionStatus !== 'connected') return 'api_offline'
  return null
}

export function timelineDropRejectMessage(reason: TimelineDropRejectReason): string {
  if (reason === 'playing') return tKey('timeline_drop_playing')
  if (reason === 'api_offline') return tKey('timeline_drop_api_offline')
  if (reason === 'preview_stop_timeout') return tKey('timeline_drop_preview_stop_timeout')
  return tKey('timeline_drop_failed')
}

async function ensureTimelineImportReady(): Promise<TimelineDropRejectReason> {
  const prep = await prepareTimelineImport()
  if (!prep.ok) return prep.reason
  return timelineDropGuard()
}

export async function runTimelineProjectJsonDrop(
  file: File,
): Promise<TimelineProjectJsonDropResult> {
  const blocked = await ensureTimelineImportReady()
  if (blocked === 'playing') return { kind: 'playing' }
  if (blocked === 'preview_stop_timeout') return { kind: 'preview_stop_timeout' }

  const parsed = await parseProjectImportFile(file)
  if (!parsed.ok) {
    return { kind: 'invalid', filename: parsed.filename, messageKey: parsed.messageKey }
  }

  return { kind: 'ready', payload: parsed.payload, filename: parsed.filename }
}

export async function runTimelineFileDrop(
  files: File[],
  onProgress: (current: number, total: number, kind?: 'image' | 'video' | 'audio') => void,
): Promise<{ result: TimelineDropResult; rejected: TimelineDropRejectReason }> {
  const blocked = await ensureTimelineImportReady()
  if (blocked) {
    return {
      rejected: blocked,
      result: { succeeded: 0, failed: [] },
    }
  }

  if (files.length === 0) {
    return {
      rejected: 'no_files',
      result: { succeeded: 0, failed: [] },
    }
  }

  const result = await runTimelineImport(files, onProgress)
  return { result, rejected: null }
}
