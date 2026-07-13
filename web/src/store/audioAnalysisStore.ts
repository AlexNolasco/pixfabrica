import { create } from 'zustand'
import type { AudioAnalyzeJobState } from '@/lib/audioAnalysis'

interface AudioAnalysisState {
  jobs: Record<string, AudioAnalyzeJobState | undefined>
  setJobForSound: (soundId: string, job: AudioAnalyzeJobState | undefined) => void
  patchJobForSound: (
    soundId: string,
    patch: Partial<AudioAnalyzeJobState> & { jobId: string; signature: string },
  ) => void
}

export const useAudioAnalysisStore = create<AudioAnalysisState>((set) => ({
  jobs: {},
  setJobForSound: (soundId, job) =>
    set((s) => ({
      jobs: job === undefined ? omitKey(s.jobs, soundId) : { ...s.jobs, [soundId]: job },
    })),
  patchJobForSound: (soundId, patch) =>
    set((s) => {
      const prev = s.jobs[soundId]
      if (!prev) return s
      return {
        jobs: {
          ...s.jobs,
          [soundId]: { ...prev, ...patch },
        },
      }
    }),
}))

function omitKey<T extends Record<string, unknown>>(obj: T, key: string): T {
  const next = { ...obj }
  delete next[key]
  return next
}

export function selectSoundAnalysisJob(soundId: string) {
  return (s: AudioAnalysisState) => s.jobs[soundId]
}
