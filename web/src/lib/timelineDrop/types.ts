import type { AnalyzerKind } from '@/lib/sound'

export interface TimelineDropProgress {
  current: number
  total: number
}

export interface TimelineDropFailure {
  name: string
  message: string
}

export interface TimelineDropResult {
  succeeded: number
  failed: TimelineDropFailure[]
  /** Last image in drop order (front-most). */
  frontTrackId?: string
  frontClipId?: string
  /** Last audio in drop order (front-most row). */
  frontSoundId?: string
}

export interface VisualTrackDropBatchItem {
  trackLabel: string
  clipLabel: string
  clipType: string
  params: Record<string, unknown>
  /** Explicit clip length in seconds; omit to inherit project duration. */
  clipDuration?: number
}

export interface AudioDropBatchItem {
  bus: string
  source: string
  volume: number
  seek: number
  analyzer: AnalyzerKind
  beat_tightness: number
  start: number
  duration: number | null
  enabled: boolean
}

export interface TimelineImportBatch {
  visualTracks: VisualTrackDropBatchItem[]
  sounds: AudioDropBatchItem[]
  /** Layout order (back → front); reversed when prepending to timeline. */
  layoutOrder: Array<{ kind: 'track'; trackIndex: number } | { kind: 'sound'; soundIndex: number }>
}

export interface TimelineImportPlacement {
  frontTrackId?: string
  frontClipId?: string
  frontSoundId?: string
}
