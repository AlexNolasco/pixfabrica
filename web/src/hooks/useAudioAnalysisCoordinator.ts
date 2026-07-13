import { useEffect, useRef } from 'react'
import {
  audioAnalysisSignature,
  cancelAudioAnalysis,
  fetchAudioAnalysisStatus,
  formatAnalysisDuration,
  soundNeedsBackgroundAnalysis,
  startAudioAnalysis,
  type AudioAnalyzeStatus,
} from '@/lib/audioAnalysis'
import { useT } from '@/lib/i18n'
import { requestPreviewRefresh } from '@/lib/previewRefresh'
import { selectSoundAnalysisJob, useAudioAnalysisStore } from '@/store/audioAnalysisStore'
import { useProjectStore } from '@/store/projectStore'
import { useToastStore } from '@/store/toastStore'

const POLL_MS = 800

const TERMINAL: ReadonlySet<AudioAnalyzeStatus> = new Set([
  'done',
  'failed',
  'cancelled',
])

function formatBusLabel(bus: string, untitled: string): string {
  const trimmed = bus.trim()
  return trimmed || untitled
}

export function useAudioAnalysisCoordinator(): void {
  const t = useT()
  const sounds = useProjectStore((s) => s.sounds)
  const meta = useProjectStore((s) => s.meta)
  const apiConnectionStatus = useProjectStore((s) => s.apiConnectionStatus)
  const appendEventLog = useProjectStore((s) => s.appendEventLog)
  const setJobForSound = useAudioAnalysisStore((s) => s.setJobForSound)
  const patchJobForSound = useAudioAnalysisStore((s) => s.patchJobForSound)
  const pushToast = useToastStore((s) => s.pushToast)
  const startingRef = useRef<Set<string>>(new Set())

  const reportAnalysisComplete = (bus: string, startedAtMs: number) => {
    const duration = formatAnalysisDuration(performance.now() - startedAtMs)
    pushToast(t('toast_librosa_complete').replace('{bus}', bus))
    appendEventLog(
      'info',
      t('event_librosa_complete')
        .replace('{bus}', bus)
        .replace('{duration}', duration),
    )
    requestPreviewRefresh(true)
  }

  const reportAnalysisFailed = (bus: string, message?: string) => {
    pushToast(t('toast_librosa_failed').replace('{bus}', bus), 'error')
    const detail = message ? ` — ${message}` : ''
    appendEventLog(
      'error',
      t('event_librosa_failed').replace('{bus}', bus) + detail,
    )
  }

  useEffect(() => {
    if (apiConnectionStatus !== 'connected') return

    const jobs = useAudioAnalysisStore.getState().jobs
    const soundIds = new Set(sounds.map((s) => s.id))

    for (const soundId of Object.keys(jobs)) {
      if (soundIds.has(soundId)) continue
      const job = jobs[soundId]
      if (job && !TERMINAL.has(job.status)) {
        void cancelAudioAnalysis(job.jobId).catch(() => undefined)
      }
      setJobForSound(soundId, undefined)
    }

    for (const sound of sounds) {
      const job = useAudioAnalysisStore.getState().jobs[sound.id]
      const signature = audioAnalysisSignature(sound, meta.fps)

      if (!soundNeedsBackgroundAnalysis(sound, meta.fps, job)) {
        continue
      }

      if (startingRef.current.has(sound.id)) continue

      if (job && job.signature !== signature && !TERMINAL.has(job.status)) {
        void cancelAudioAnalysis(job.jobId).catch(() => undefined)
      }

      startingRef.current.add(sound.id)
      const startedAtMs = performance.now()
      void (async () => {
        try {
          const res = await startAudioAnalysis(sound, meta.fps)
          setJobForSound(sound.id, {
            jobId: res.job_id,
            signature,
            status: res.status,
            progress: res.progress,
            error: null,
            startedAtMs,
          })
          const bus = formatBusLabel(sound.bus, t('sound_untitled'))
          if (res.status === 'done') {
            reportAnalysisComplete(bus, startedAtMs)
          } else {
            pushToast(t('toast_librosa_started').replace('{bus}', bus))
            appendEventLog(
              'info',
              t('event_librosa_started').replace('{bus}', bus),
            )
          }
        } catch (e) {
          const message = e instanceof Error ? e.message : String(e)
          setJobForSound(sound.id, {
            jobId: job?.jobId ?? 'failed',
            signature,
            status: 'failed',
            progress: 0,
            error: message,
            startedAtMs,
          })
          const bus = formatBusLabel(sound.bus, t('sound_untitled'))
          reportAnalysisFailed(bus, message)
        } finally {
          startingRef.current.delete(sound.id)
        }
      })()
    }
  }, [
    sounds,
    meta.fps,
    apiConnectionStatus,
    setJobForSound,
    pushToast,
    appendEventLog,
    t,
  ])

  useEffect(() => {
    if (apiConnectionStatus !== 'connected') return

    let cancelled = false

    const poll = async () => {
      if (cancelled) return
      const jobs = useAudioAnalysisStore.getState().jobs
      const { sounds: currentSounds } = useProjectStore.getState()

      for (const [soundId, job] of Object.entries(jobs)) {
        if (!job || TERMINAL.has(job.status)) continue
        try {
          const st = await fetchAudioAnalysisStatus(job.jobId)
          const prevStatus = job.status
          patchJobForSound(soundId, {
            jobId: job.jobId,
            signature: job.signature,
            status: st.status,
            progress: st.progress,
            error: st.error,
          })

          if (prevStatus !== 'done' && st.status === 'done') {
            const sound = currentSounds.find((s) => s.id === soundId)
            if (!sound) continue
            const sig = audioAnalysisSignature(sound, meta.fps)
            if (sig !== job.signature) continue
            const bus = formatBusLabel(sound.bus, t('sound_untitled'))
            reportAnalysisComplete(bus, job.startedAtMs)
          } else if (prevStatus !== 'failed' && st.status === 'failed') {
            const sound = currentSounds.find((s) => s.id === soundId)
            if (!sound) continue
            const bus = formatBusLabel(sound.bus, t('sound_untitled'))
            reportAnalysisFailed(bus, st.error ?? undefined)
          }
        } catch {
          // ignore transient poll errors
        }
      }
    }

    const id = window.setInterval(() => void poll(), POLL_MS)
    return () => {
      cancelled = true
      window.clearInterval(id)
    }
  }, [apiConnectionStatus, meta.fps, patchJobForSound, pushToast, appendEventLog, t])
}

export function useSoundIsAnalyzing(soundId: string): boolean {
  const job = useAudioAnalysisStore(selectSoundAnalysisJob(soundId))
  return job?.status === 'queued' || job?.status === 'running'
}
