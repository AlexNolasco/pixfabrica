import { apiDelete, apiGet, apiPost } from '@/lib/apiClient'
import type { AnalyzerKind, Sound } from '@/lib/sound'
import { DEFAULT_ANALYZER, soundHasRequirements } from '@/lib/sound'

export type AudioAnalyzeStatus = 'queued' | 'running' | 'done' | 'failed' | 'cancelled'

export interface AudioAnalyzeJobState {
  jobId: string
  signature: string
  status: AudioAnalyzeStatus
  progress: number
  error: string | null
  /** `performance.now()` when the background job was requested. */
  startedAtMs: number
}

/** Human-readable analysis duration for event log. */
export function formatAnalysisDuration(ms: number): string {
  if (ms < 1000) return `${Math.max(0, Math.round(ms))} ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)} s`
  const minutes = Math.floor(ms / 60_000)
  const seconds = Math.round((ms % 60_000) / 1000)
  return seconds > 0 ? `${minutes} m ${seconds} s` : `${minutes} m`
}

export interface AnalyzeStartResponse {
  job_id: string
  status: AudioAnalyzeStatus
  progress: number
}

export interface AnalyzeStatusResponse {
  job_id: string
  status: AudioAnalyzeStatus
  progress: number
  error: string | null
}

/** Cache-key inputs shared with the API / SoundClip NPZ path. */
export function audioAnalysisSignature(
  sound: Pick<Sound, 'source' | 'seek' | 'duration' | 'beat_tightness' | 'analyzer'>,
  fps: number,
): string {
  return JSON.stringify({
    source: sound.source,
    seek: sound.seek,
    duration: sound.duration,
    beat_tightness: sound.beat_tightness,
    fps,
    analyzer: DEFAULT_ANALYZER,
  })
}

export function soundNeedsBackgroundAnalysis(
  sound: Sound,
  fps: number,
  job: AudioAnalyzeJobState | undefined,
): boolean {
  if (!soundHasRequirements(sound)) return false
  const sig = audioAnalysisSignature(sound, fps)
  if (job?.signature === sig && job.status === 'done') return false
  return true
}

/** @deprecated Legacy name — always uses StemAnalyzer now. */
export function soundNeedsLibrosaAnalysis(
  sound: Sound,
  fps: number,
  job: AudioAnalyzeJobState | undefined,
): boolean {
  if (!soundHasRequirements(sound)) return false
  return soundNeedsBackgroundAnalysis(sound, fps, job)
}

export async function startAudioAnalysis(
  sound: Sound,
  fps: number,
  analyzer: AnalyzerKind = DEFAULT_ANALYZER,
): Promise<AnalyzeStartResponse> {
  return apiPost<AnalyzeStartResponse>('/audio/analyze', {
    source: sound.source,
    seek: sound.seek,
    duration: sound.duration,
    fps,
    beat_tightness: sound.beat_tightness,
    analyzer,
  })
}

/** @deprecated Use startAudioAnalysis */
export async function startLibrosaAnalysis(
  sound: Sound,
  fps: number,
): Promise<AnalyzeStartResponse> {
  return startAudioAnalysis(sound, fps, 'stem')
}

export async function fetchAudioAnalysisStatus(jobId: string): Promise<AnalyzeStatusResponse> {
  return apiGet<AnalyzeStatusResponse>(`/audio/analyze/${jobId}`)
}

/** @deprecated Use fetchAudioAnalysisStatus */
export async function fetchLibrosaAnalysisStatus(jobId: string): Promise<AnalyzeStatusResponse> {
  return fetchAudioAnalysisStatus(jobId)
}

export async function cancelAudioAnalysis(jobId: string): Promise<AnalyzeStatusResponse> {
  return apiDelete<AnalyzeStatusResponse>(`/audio/analyze/${jobId}`)
}

/** @deprecated Use cancelAudioAnalysis */
export async function cancelLibrosaAnalysis(jobId: string): Promise<AnalyzeStatusResponse> {
  return cancelAudioAnalysis(jobId)
}
