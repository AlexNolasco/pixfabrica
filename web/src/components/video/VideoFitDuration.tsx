import { useCallback, useEffect, useMemo, useState } from 'react'
import { formatTime } from '@/lib/formatTime'
import { useT } from '@/lib/i18n'
import { apiCreateVideoBoomerang, apiCreateVideoReverse, projectUploadTarget } from '@/lib/mediaUpload'
import { canAddClipToTrack } from '@/lib/projectLimits'
import { computeVideoClipFit } from '@/lib/videoFit'
import { computeVideoBoomerangPlan, isBoomerangDerivativeSource } from '@/lib/videoBoomerang'
import { computeVideoReversePlan } from '@/lib/videoReverse'
import { fetchVideoDuration, invalidateVideoDuration } from '@/lib/videoDurationCache'
import { useProjectStore, type Clip as TimelineClip } from '@/store/projectStore'

type DecodeState = 'idle' | 'loading' | 'ready' | 'error'

export function VideoFitDuration({
  trackId,
  clip,
  source,
  startOffset,
  playbackRate,
}: {
  trackId: string
  clip: TimelineClip
  source: string
  startOffset: unknown
  playbackRate: unknown
}) {
  if (!clip) return null
  const t = useT()
  const meta = useProjectStore((s) => s.meta)
  const serverConfig = useProjectStore((s) => s.serverConfig)
  const track = useProjectStore((s) => s.tracks.find((row) => row.id === trackId))
  const updateClip = useProjectStore((s) => s.updateClip)
  const insertClipCloneAfter = useProjectStore((s) => s.insertClipCloneAfter)

  const canAddCopy = useMemo(
    () => (track ? canAddClipToTrack(track, serverConfig) : false),
    [track, serverConfig],
  )

  const [decodeState, setDecodeState] = useState<DecodeState>('idle')
  const [sourceDuration, setSourceDuration] = useState<number | null>(null)
  const [boomerangBusy, setBoomerangBusy] = useState(false)
  const [boomerangError, setBoomerangError] = useState<string | null>(null)
  const [reverseBusy, setReverseBusy] = useState(false)
  const [reverseError, setReverseError] = useState<string | null>(null)

  const trimmedSource = source.trim()
  const hasSource = trimmedSource.length > 0
  const isBoomerangSource = useMemo(
    () => isBoomerangDerivativeSource(trimmedSource),
    [trimmedSource],
  )
  const canCreateBoomerang = canAddCopy && !isBoomerangSource

  useEffect(() => {
    if (!hasSource) {
      setDecodeState('idle')
      setSourceDuration(null)
      return
    }
    let cancelled = false
    setDecodeState('loading')
    setSourceDuration(null)
    void fetchVideoDuration(trimmedSource).then((duration) => {
      if (cancelled) return
      if (duration == null || duration <= 0) {
        setDecodeState('error')
        setSourceDuration(null)
        return
      }
      setSourceDuration(duration)
      setDecodeState('ready')
    })
    return () => {
      cancelled = true
    }
  }, [hasSource, trimmedSource])

  const fitParams = useMemo(
    () => ({ start_offset: startOffset, playback_rate: playbackRate }),
    [startOffset, playbackRate],
  )

  const fit = useMemo(() => {
    if (sourceDuration == null || !track) return null
    return computeVideoClipFit(
      sourceDuration,
      fitParams,
      track.start,
      clip.start,
      meta,
    )
  }, [sourceDuration, track, fitParams, clip.start, meta])

  const boomerang = useMemo(() => {
    if (sourceDuration == null || !track) return null
    return computeVideoBoomerangPlan(
      sourceDuration,
      fitParams,
      track.start,
      clip.start,
      meta,
    )
  }, [sourceDuration, track, fitParams, clip.start, meta])

  const reversePlan = useMemo(() => {
    if (sourceDuration == null) return null
    return computeVideoReversePlan(sourceDuration, fitParams, meta)
  }, [sourceDuration, fitParams, meta])

  const applyFit = useCallback(() => {
    if (fit == null) return
    updateClip(trackId, clip.id, { duration: fit.duration })
  }, [fit, updateClip, trackId, clip.id])

  const createBoomerang = useCallback(async () => {
    if (boomerang == null || !track || !canCreateBoomerang) return
    setBoomerangError(null)
    setBoomerangBusy(true)
    const absoluteStart = track.start + clip.start
    const maxDuration = Math.max(1 / meta.fps, meta.duration - absoluteStart)
    const target = projectUploadTarget()
    try {
      const res = await apiCreateVideoBoomerang({
        source: trimmedSource,
        start_offset: typeof startOffset === 'number' ? startOffset : 0,
        playback_rate: typeof playbackRate === 'number' && playbackRate > 0 ? playbackRate : 1,
        max_duration: maxDuration,
        target_fps: target.target_fps,
        target_width: target.target_width,
        target_height: target.target_height,
      })
      invalidateVideoDuration(res.path)
      const cloneId = insertClipCloneAfter(trackId, clip.id, {
        duration: res.duration,
        params: {
          ...clip.params,
          source: res.path,
          start_offset: 0,
          playback_rate: 1,
        },
      })
      if (cloneId == null) {
        setBoomerangError(t('video_boomerang_track_full'))
      }
    } catch (err) {
      setBoomerangError(err instanceof Error ? err.message : t('video_boomerang_failed'))
    } finally {
      setBoomerangBusy(false)
    }
  }, [
    boomerang,
    track,
    clip,
    canCreateBoomerang,
    meta.fps,
    meta.duration,
    trimmedSource,
    startOffset,
    playbackRate,
    insertClipCloneAfter,
    trackId,
    t,
  ])

  const bakeReverse = useCallback(async () => {
    if (reversePlan == null) return
    setReverseError(null)
    setReverseBusy(true)
    const target = projectUploadTarget()
    try {
      const res = await apiCreateVideoReverse({
        source: trimmedSource,
        start_offset: typeof startOffset === 'number' ? startOffset : 0,
        playback_rate: typeof playbackRate === 'number' && playbackRate > 0 ? playbackRate : 1,
        target_fps: target.target_fps,
        target_width: target.target_width,
        target_height: target.target_height,
      })
      invalidateVideoDuration(res.path)
      updateClip(trackId, clip.id, {
        duration: res.duration,
        params: {
          ...clip.params,
          source: res.path,
          start_offset: 0,
          playback_rate: 1,
        },
      })
    } catch (err) {
      setReverseError(err instanceof Error ? err.message : t('video_reverse_failed'))
    } finally {
      setReverseBusy(false)
    }
  }, [
    reversePlan,
    trimmedSource,
    startOffset,
    playbackRate,
    updateClip,
    trackId,
    clip,
    t,
  ])

  const derivativeBusy = boomerangBusy || reverseBusy

  if (!hasSource) return null

  return (
    <div className="flex flex-col gap-1.5 rounded border border-border px-2 py-1.5">
      {decodeState === 'loading' ? (
        <p className="text-[10px] text-muted-foreground">{t('video_fit_decode_loading')}</p>
      ) : null}
      {decodeState === 'error' ? (
        <p className="text-[10px] text-destructive">{t('video_fit_decode_failed')}</p>
      ) : null}
      {decodeState === 'ready' && sourceDuration != null && fit != null ? (
        <p className="text-[10px] text-muted-foreground">
          {(fit.capped ? t('video_fit_duration_capped_hint') : t('video_fit_duration_hint'))
            .replace('{file}', formatTime(sourceDuration))
            .replace('{clip}', formatTime(fit.duration))}
        </p>
      ) : null}
      {decodeState === 'ready' && sourceDuration != null && reversePlan != null ? (
        <p className="text-[10px] text-muted-foreground">
          {t('video_reverse_hint')
            .replace('{file}', formatTime(sourceDuration))
            .replace('{clip}', formatTime(reversePlan.outputDuration))}
        </p>
      ) : null}
      {decodeState === 'ready' && sourceDuration != null && boomerang != null && !isBoomerangSource ? (
        <p className="text-[10px] text-muted-foreground">
          {(boomerang.capped
            ? t('video_boomerang_duration_capped_hint')
            : boomerang.cycles > 1
              ? t('video_boomerang_duration_tiled_hint')
              : t('video_boomerang_duration_hint'))
            .replace('{file}', formatTime(sourceDuration))
            .replace('{clip}', formatTime(boomerang.outputDuration))
            .replace('{cycles}', String(boomerang.cycles))}
        </p>
      ) : null}
      {isBoomerangSource ? (
        <p className="text-[10px] text-muted-foreground">{t('video_boomerang_already_derivative')}</p>
      ) : null}
      {!canAddCopy && !isBoomerangSource ? (
        <p className="text-[10px] text-muted-foreground">{t('video_boomerang_track_full')}</p>
      ) : null}
      <div className="flex flex-wrap gap-1.5">
        <button
          type="button"
          disabled={decodeState !== 'ready' || fit == null || derivativeBusy}
          className="w-fit rounded border border-border px-2 py-1 text-xs hover:bg-muted/60 disabled:cursor-not-allowed disabled:opacity-40"
          onClick={applyFit}
        >
          {t('video_fit_clip_duration')}
        </button>
        <button
          type="button"
          disabled={decodeState !== 'ready' || reversePlan == null || derivativeBusy}
          className="w-fit rounded border border-border px-2 py-1 text-xs hover:bg-muted/60 disabled:cursor-not-allowed disabled:opacity-40"
          onClick={() => void bakeReverse()}
        >
          {reverseBusy ? t('video_reverse_working') : t('video_reverse_apply')}
        </button>
        <button
          type="button"
          disabled={decodeState !== 'ready' || boomerang == null || derivativeBusy || !canCreateBoomerang}
          className="w-fit rounded border border-border px-2 py-1 text-xs hover:bg-muted/60 disabled:cursor-not-allowed disabled:opacity-40"
          onClick={() => void createBoomerang()}
        >
          {boomerangBusy ? t('video_boomerang_working') : t('video_boomerang_create')}
        </button>
      </div>
      {reverseError ? (
        <p className="text-[10px] text-destructive">{reverseError}</p>
      ) : null}
      {boomerangError ? (
        <p className="text-[10px] text-destructive">{boomerangError}</p>
      ) : null}
    </div>
  )
}
