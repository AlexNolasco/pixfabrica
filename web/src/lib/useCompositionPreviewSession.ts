import { useEffect, useMemo, useRef } from 'react'
import { useBrokenClipCount } from '@/lib/brokenClips'
import { useInvalidParamsCount } from '@/lib/invalidClipParams'
import { isOverProjectLimits } from '@/lib/projectLimits'
import { clipPreviewClient } from '@/lib/clipPreviewClient'
import { previewClient, requestPreviewRefresh } from '@/lib/previewClient'
import { schedulePreviewRefresh } from '@/lib/previewRefresh'
import { resetPrepareWarningDiagnostics } from '@/lib/prepareWarningDiagnostics'
import { useProjectStore } from '@/store/projectStore'

/**
 * Owns the composition preview WebSocket for the whole preview pane lifetime.
 * Paused while clip preview is visible — connection and server compositor stay warm.
 */
export function useCompositionPreviewSession(paused: boolean): void {
  const meta = useProjectStore((s) => s.meta)
  const tracks = useProjectStore((s) => s.tracks)
  const sounds = useProjectStore((s) => s.sounds)
  const typography = useProjectStore((s) => s.typography)
  const colors = useProjectStore((s) => s.colors)
  const previewTime = useProjectStore((s) => s.previewTime)
  const isPlaying = useProjectStore((s) => s.isPlaying)
  const apiConnectionStatus = useProjectStore((s) => s.apiConnectionStatus)
  const serverConfig = useProjectStore((s) => s.serverConfig)
  const brokenClipCount = useBrokenClipCount()
  const invalidParamsCount = useInvalidParamsCount()
  const previewBlocked = brokenClipCount > 0 || invalidParamsCount > 0

  const overLimits = useMemo(
    () => isOverProjectLimits(tracks, sounds, serverConfig, meta),
    [tracks, sounds, serverConfig, meta],
  )

  const graphFingerprint = useMemo(
    () => JSON.stringify({ meta, tracks, sounds, typography, colors }),
    [meta, tracks, sounds, typography, colors],
  )

  const canConnect =
    apiConnectionStatus === 'connected' && !overLimits && !previewBlocked

  const prevGraphFingerprintRef = useRef(graphFingerprint)
  const wasCanConnectRef = useRef(false)
  const pausedRef = useRef(paused)
  pausedRef.current = paused

  useEffect(() => {
    previewClient.setEnabled(canConnect)
    if (canConnect && !wasCanConnectRef.current && !pausedRef.current) {
      requestPreviewRefresh(true)
    }
    wasCanConnectRef.current = canConnect
    return () => previewClient.setEnabled(false)
  }, [canConnect])

  useEffect(() => {
    if ((overLimits || previewBlocked) && isPlaying) {
      useProjectStore.getState().setIsPlaying(false)
    }
  }, [overLimits, previewBlocked, isPlaying])

  useEffect(() => {
    if (!canConnect) return
    if (paused) {
      previewClient.pause()
      return
    }
    const needsReprepareAfterGl = clipPreviewClient.hadGlPreview()
    let cancelled = false
    // Ensure clip preview socket is torn down before composition GL resumes.
    clipPreviewClient.setEnabled(false)
    void clipPreviewClient.whenIdle().then(() => {
      if (cancelled) return
      clipPreviewClient.clearGlPreviewFlag()
      const needsReprepare =
        !previewClient.isWarmForCurrentGraph() || needsReprepareAfterGl
      previewClient.resume(needsReprepare)
      if (needsReprepare) {
        previewClient.requestReprepare()
      } else {
        requestPreviewRefresh()
      }
    })
    return () => {
      cancelled = true
    }
  }, [paused, canConnect])

  useEffect(() => {
    if (!canConnect) return
    if (prevGraphFingerprintRef.current === graphFingerprint) return
    prevGraphFingerprintRef.current = graphFingerprint

    if (paused) {
      previewClient.markGraphStale()
      return
    }
    if (isPlaying) {
      previewClient.deferGraphRefresh()
      return
    }
    requestPreviewRefresh(true)
  }, [paused, canConnect, isPlaying, graphFingerprint])

  useEffect(() => {
    if (paused || !canConnect || isPlaying) return
    schedulePreviewRefresh()
  }, [paused, canConnect, isPlaying, previewTime])

  useEffect(() => {
    if (paused) {
      previewClient.setPlayPump(false)
      return
    }
    previewClient.setPlayPump(isPlaying && canConnect)
    return () => previewClient.setPlayPump(false)
  }, [paused, isPlaying, canConnect])

  useEffect(() => {
    if (paused) return
    resetPrepareWarningDiagnostics()
  }, [graphFingerprint, paused])
}
