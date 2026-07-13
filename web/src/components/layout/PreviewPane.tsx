import { Download, Loader2, Pause, Play, Square, Volume2, VolumeX } from 'lucide-react'
import { isClipSelection } from '@/lib/selection'
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { Button } from '@/components/ui/button'
import { useT } from '@/lib/i18n'
import {
  previewAspectRatio,
  previewDimensionsFromMeta,
} from '@/lib/previewDimensions'
import {
  clipPreviewClient,
  type ClipPreviewConnectionStatus,
} from '@/lib/clipPreviewClient'
import { setClipPreviewAudioOptions } from '@/lib/clipPreviewAudio'
import { catalogDetailCacheKey } from '@/lib/catalogDetail'
import {
  clipNeedsBusPreview,
  loadPreviewSamples,
  pickDefaultSample,
  type PreviewSample,
} from '@/lib/previewSamples'
import {
  flushClipPreviewRefresh,
  scheduleClipPreviewRefresh,
} from '@/lib/clipPreviewRefresh'
import { LIVE_PREVIEW_ENABLED, CLIP_ISOLATED_PREVIEW_ENABLED } from '@/lib/previewConfig'
import {
  effectiveClipPreviewMode,
  trackSupportsClipPreview,
} from '@/lib/clipPreviewMode'
import { enterClipPreviewFromToggle } from '@/lib/previewTransport'
import {
  isPreviewFrameStale,
  previewClient,
  type PreviewConnectionStatus,
} from '@/lib/previewClient'
import {
  formatLimitViolation,
  getProjectLimitViolations,
  isOverProjectLimits,
} from '@/lib/projectLimits'
import { ProjectLimitsBanner } from '@/components/layout/ProjectLimitsBanner'
import { useCompositionPreviewSession } from '@/lib/useCompositionPreviewSession'
import {
  downloadPngFromCanvas,
  downloadPngFromRgba,
  previewFrameFilename,
} from '@/lib/exportPreviewFrame'
import {
  formatPreviewBlockedMessage,
  useBrokenClipCount,
  useIsClipBroken,
} from '@/lib/brokenClips'
import {
  formatPreviewInvalidParamsMessage,
  useInvalidParamFields,
  useInvalidParamsCount,
} from '@/lib/invalidClipParams'
import { usePreviewCanvasColorPick } from '@/lib/usePreviewCanvasColorPick'
import { useToastStore } from '@/store/toastStore'
import { useProjectStore } from '@/store/projectStore'

/** Right strip width — timeline uses an empty spacer so the canvas box matches clip mode. */
export const CLIP_PREVIEW_CONTROLS_WIDTH_PX = 52
export const COMPOSITION_PREVIEW_CONTROLS_WIDTH_PX = CLIP_PREVIEW_CONTROLS_WIDTH_PX

type PreviewLayoutContextValue = {
  reportFrameSize: (width: number, height: number) => void
  displayAspect: number
}

const PreviewLayoutContext = createContext<PreviewLayoutContextValue | null>(null)

function usePreviewLayout(): PreviewLayoutContextValue {
  const ctx = useContext(PreviewLayoutContext)
  if (!ctx) {
    throw new Error('PreviewLayoutContext missing')
  }
  return ctx
}

function usePreviewLayoutState(meta: { width: number; height: number }): PreviewLayoutContextValue {
  const maxPreviewLongSide = useProjectStore((s) => s.serverConfig.maxPreviewLongSide)
  const [frameSize, setFrameSize] = useState<{ width: number; height: number } | null>(null)

  useEffect(() => {
    setFrameSize(null)
  }, [meta.width, meta.height])

  const reportFrameSize = useCallback((width: number, height: number) => {
    setFrameSize((prev) =>
      prev?.width === width && prev?.height === height ? prev : { width, height },
    )
  }, [])

  const displayAspect = useMemo(() => {
    if (frameSize && frameSize.width > 0 && frameSize.height > 0) {
      return frameSize.width / frameSize.height
    }
    const dims = previewDimensionsFromMeta(meta, maxPreviewLongSide)
    return dims.width / dims.height
  }, [frameSize, meta.width, meta.height, maxPreviewLongSide])

  return useMemo(
    () => ({ reportFrameSize, displayAspect }),
    [reportFrameSize, displayAspect],
  )
}

function PreviewPaneDisabled() {
  const t = useT()
  const meta = useProjectStore((s) => s.meta)
  const layout = usePreviewLayoutState(meta)
  const aspect = previewAspectRatio(meta.width, meta.height)

  return (
    <PreviewLayoutContext.Provider value={layout}>
      <div className="flex h-full w-full min-w-0 items-center justify-center overflow-hidden bg-black/80 [container-type:size]">
        <div
          className="relative flex items-center justify-center bg-black border border-white/10"
          style={{
            aspectRatio: `${aspect}`,
            width: `min(100cqw, calc(100cqh * ${aspect}))`,
            height: `min(100cqh, calc(100cqw / ${aspect}))`,
          }}
        >
          <p className="text-white/30 text-sm select-none px-4 text-center">
            {t('preview_disabled')} — {meta.width}×{meta.height} @ {meta.fps}fps
          </p>
        </div>
      </div>
    </PreviewLayoutContext.Provider>
  )
}

function usePreviewCanvas() {
  const { reportFrameSize } = usePreviewLayout()
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const imageDataRef = useRef<ImageData | null>(null)
  const [hasFrame, setHasFrame] = useState(false)

  const blitFrame = useCallback(
    (width: number, height: number, rgba: Uint8ClampedArray) => {
      const canvas = canvasRef.current
      if (!canvas) return
      const ctx = canvas.getContext('2d')
      if (!ctx) return

      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width
        canvas.height = height
        imageDataRef.current = null
      }

      let image = imageDataRef.current
      if (!image || image.width !== width || image.height !== height) {
        image = new ImageData(width, height)
        imageDataRef.current = image
      }
      image.data.set(rgba)
      ctx.putImageData(image, 0, 0)
      reportFrameSize(width, height)
      setHasFrame(true)
    },
    [reportFrameSize],
  )

  const clearFrame = useCallback(() => setHasFrame(false), [])

  return { canvasRef, hasFrame, blitFrame, clearFrame }
}

function TimelinePreviewLive() {
  const t = useT()
  const meta = useProjectStore((s) => s.meta)
  const tracks = useProjectStore((s) => s.tracks)
  const sounds = useProjectStore((s) => s.sounds)
  const typography = useProjectStore((s) => s.typography)
  const colors = useProjectStore((s) => s.colors)
  const previewTime = useProjectStore((s) => s.previewTime)
  const isPlaying = useProjectStore((s) => s.isPlaying)
  const apiConnectionStatus = useProjectStore((s) => s.apiConnectionStatus)
  const serverConfig = useProjectStore((s) => s.serverConfig)
  const appendEventLog = useProjectStore((s) => s.appendEventLog)
  const locale = useProjectStore((s) => s.appSettings.locale)
  const brokenClipCount = useBrokenClipCount()
  const hasBrokenClips = brokenClipCount > 0
  const invalidParamsCount = useInvalidParamsCount()
  const hasInvalidParams = invalidParamsCount > 0
  const previewBlocked = hasBrokenClips || hasInvalidParams

  const overLimits = useMemo(
    () => isOverProjectLimits(tracks, sounds, serverConfig, meta),
    [tracks, sounds, serverConfig, meta],
  )

  const limitOverlayMessage = useMemo(() => {
    if (!overLimits) return null
    const violations = getProjectLimitViolations(tracks, sounds, serverConfig, meta)
    return violations.map((v) => formatLimitViolation(v, locale)).join(' · ')
  }, [overLimits, tracks, sounds, serverConfig, meta, locale])

  const graphFingerprint = useMemo(
    () => JSON.stringify({ meta, tracks, sounds, typography, colors }),
    [meta, tracks, sounds, typography, colors],
  )

  const pushToast = useToastStore((s) => s.pushToast)
  const thumbnailExportResolution = useProjectStore(
    (s) => s.appSettings.thumbnailExportResolution,
  )

  const { canvasRef, hasFrame, blitFrame, clearFrame } = usePreviewCanvas()
  const { pickActive, onCanvasPointerDown } = usePreviewCanvasColorPick(canvasRef, hasFrame)
  const [status, setStatus] = useState<PreviewConnectionStatus>('idle')
  const [waitingFrame, setWaitingFrame] = useState(false)
  const [frameMatchesGraph, setFrameMatchesGraph] = useState(false)
  const [exportingFrame, setExportingFrame] = useState(false)
  const prevGraphFingerprintRef = useRef(graphFingerprint)
  const warmCacheAppliedRef = useRef(false)

  const applyWarmCachedFrame = useCallback(() => {
    if (isPlaying) return false
    if (!previewClient.isWarmForCurrentGraph()) return false
    const cached = previewClient.getLastFrame()
    if (!cached) return false
    blitFrame(cached.width, cached.height, cached.rgba)
    setFrameMatchesGraph(true)
    setWaitingFrame(false)
    return true
  }, [blitFrame, isPlaying])

  useEffect(() => {
    if (prevGraphFingerprintRef.current === graphFingerprint) return
    prevGraphFingerprintRef.current = graphFingerprint
    if (isPlaying) return
    if (!applyWarmCachedFrame()) {
      setFrameMatchesGraph(false)
    }
  }, [graphFingerprint, applyWarmCachedFrame, isPlaying])

  useEffect(() => {
    if (!overLimits && !previewBlocked && apiConnectionStatus === 'connected') return
    clearFrame()
    setWaitingFrame(false)
    setFrameMatchesGraph(false)
  }, [apiConnectionStatus, overLimits, previewBlocked, clearFrame])

  useLayoutEffect(() => {
    if (warmCacheAppliedRef.current) return
    if (applyWarmCachedFrame()) {
      warmCacheAppliedRef.current = true
    }
  }, [applyWarmCachedFrame])

  useEffect(() => previewClient.onStatus(setStatus), [])
  useEffect(() => {
    return previewClient.onError((message) => {
      appendEventLog('error', `${t('preview_error')}: ${message}`)
      setWaitingFrame(false)
    })
  }, [appendEventLog, t])

  useEffect(() => {
    return previewClient.onFrame(({ width, height, rgba, t: frameT }) => {
      if (isPreviewFrameStale(frameT)) {
        if (useProjectStore.getState().isPlaying) {
          previewClient.requestRefreshAfterStale()
        }
        return
      }
      blitFrame(width, height, rgba)
      setWaitingFrame(false)
      setFrameMatchesGraph(true)
      previewClient.notifyFrameDisplayed()
    })
  }, [blitFrame])

  const hasTimelineContent = tracks.length > 0 || sounds.length > 0
  const canDownloadFrame =
    !isPlaying && hasFrame && frameMatchesGraph && hasTimelineContent
  const graphStale = !frameMatchesGraph
  const showOverlay =
    overLimits ||
    previewBlocked ||
    apiConnectionStatus !== 'connected' ||
    status === 'connecting' ||
    graphStale ||
    (!hasFrame && waitingFrame)
  const overlayMessage =
    overLimits && limitOverlayMessage
      ? limitOverlayMessage
      : hasBrokenClips
        ? formatPreviewBlockedMessage(brokenClipCount)
        : hasInvalidParams
          ? formatPreviewInvalidParamsMessage(invalidParamsCount)
      : apiConnectionStatus !== 'connected'
      ? t('preview_waiting_api')
      : status === 'connecting'
        ? t('preview_connecting')
        : graphStale
          ? t('preview_preparing')
          : !hasFrame && waitingFrame
            ? t('preview_loading')
            : !hasFrame
              ? `${t('preview_placeholder')} — ${meta.width}×${meta.height} @ ${meta.fps}fps`
              : null

  const downloadCurrentFrame = useCallback(async () => {
    if (!canDownloadFrame || exportingFrame) return
    const canvas = canvasRef.current
    const filename = previewFrameFilename(meta.title, previewTime)
    setExportingFrame(true)
    try {
      if (thumbnailExportResolution === 'preview') {
        if (!canvas) throw new Error('no canvas')
        await downloadPngFromCanvas(canvas, filename)
        pushToast(t('composition_preview_download_success'))
        return
      }
      try {
        const frame = await previewClient.requestSnapshot(true)
        await downloadPngFromRgba(frame.width, frame.height, frame.rgba, filename)
        pushToast(t('composition_preview_download_success'))
      } catch {
        if (!canvas) throw new Error('no canvas')
        await downloadPngFromCanvas(canvas, filename)
        pushToast(t('composition_preview_download_fallback'))
      }
    } catch {
      pushToast(t('composition_preview_download_error'), 'error')
    } finally {
      setExportingFrame(false)
    }
  }, [
    canDownloadFrame,
    exportingFrame,
    meta.title,
    previewTime,
    thumbnailExportResolution,
    pushToast,
    t,
  ])

  return (
    <div className="flex flex-row w-full h-full min-h-0">
      <PreviewViewport>
        <PreviewCanvasShell
          overlayMessage={showOverlay ? overlayMessage : null}
          pickActive={pickActive}
        >
          <canvas
            ref={canvasRef}
            className={`block h-full w-full [image-rendering:pixelated] ${
              pickActive ? 'cursor-crosshair' : ''
            }`}
            onPointerDown={onCanvasPointerDown}
          />
        </PreviewCanvasShell>
      </PreviewViewport>
      <CompositionPreviewControls
        canDownload={canDownloadFrame}
        exporting={exportingFrame}
        onDownload={() => void downloadCurrentFrame()}
      />
    </div>
  )
}

function ClipPreviewLive({
  trackId,
  clipId,
}: {
  trackId: string
  clipId: string
}) {
  const t = useT()
  const meta = useProjectStore((s) => s.meta)
  const tracks = useProjectStore((s) => s.tracks)
  const typography = useProjectStore((s) => s.typography)
  const colors = useProjectStore((s) => s.colors)
  const apiConnectionStatus = useProjectStore((s) => s.apiConnectionStatus)
  const previewMuted = useProjectStore((s) => s.previewMuted)
  const appendEventLog = useProjectStore((s) => s.appendEventLog)
  const appLoopSeconds = useProjectStore((s) => s.appSettings.previewClipLoopSeconds)

  const ensureCatalogDetail = useProjectStore((s) => s.ensureCatalogDetail)
  const locale = useProjectStore((s) => s.appSettings.locale)
  const catalogDetailCache = useProjectStore((s) => s.catalogDetailCache)
  const track = tracks.find((tr) => tr.id === trackId)
  const clip = track?.clips.find((el) => el.id === clipId)
  const clipBroken = useIsClipBroken(clip?.clip_type ?? '')
  const invalidParamFields = useInvalidParamFields(
    clip?.clip_type ?? '',
    clip?.params ?? {},
  )
  const paramsInvalid = !clipBroken && invalidParamFields.length > 0
  const clipDisabled = clip != null && !clip.enabled
  const previewBlocked = clipBroken || paramsInvalid
  const catalogDetail = clip
    ? catalogDetailCache[catalogDetailCacheKey(clip.clip_type, locale)]
    : undefined
  const isBusDriven = useMemo(() => {
    if (!clip) return false
    return clipNeedsBusPreview(
      clip,
      catalogDetail,
      (effectType) => catalogDetailCache[catalogDetailCacheKey(effectType, locale)],
    )
  }, [clip, catalogDetail, catalogDetailCache, locale])

  useEffect(() => {
    if (!clip) return
    void ensureCatalogDetail(clip.clip_type)
    for (const fx of clip.effects ?? []) {
      if (fx.enabled !== false) void ensureCatalogDetail(fx.effect_type)
    }
  }, [clip, ensureCatalogDetail])
  const clipKey = clip
    ? `${clip.clip_type}:${JSON.stringify(clip.params)}:${clip.enabled}:${JSON.stringify(clip.effects ?? [])}`
    : ''

  const { canvasRef, hasFrame, blitFrame, clearFrame } = usePreviewCanvas()
  const { pickActive, onCanvasPointerDown } = usePreviewCanvasColorPick(canvasRef, hasFrame)
  const [status, setStatus] = useState<ClipPreviewConnectionStatus>('idle')
  const [waitingFrame, setWaitingFrame] = useState(false)
  const [localT, setLocalT] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [loopOverride, setLoopOverride] = useState<number | null>(null)
  const [previewSamples, setPreviewSamples] = useState<PreviewSample[]>([])
  const [sampleId, setSampleId] = useState<string | null>(null)
  const [busMuted, setBusMuted] = useState(false)
  const localTRef = useRef(0)
  const playingRef = useRef(false)
  const previewAudioRef = useRef<HTMLAudioElement>(null)
  const loopSecondsRef = useRef(8)
  const loopSeconds = loopOverride ?? appLoopSeconds
  loopSecondsRef.current = loopSeconds
  const silencePreviewAudio = busMuted || previewMuted

  useEffect(() => {
    let cancelled = false
    void loadPreviewSamples().then((samples) => {
      if (!cancelled) setPreviewSamples(samples)
    })
    return () => {
      cancelled = true
    }
  }, [])

  const activeSample = useMemo(
    () => previewSamples.find((s) => s.id === sampleId) ?? null,
    [previewSamples, sampleId],
  )

  useEffect(() => {
    setSampleId((prev) => pickDefaultSample(previewSamples, prev))
  }, [previewSamples])

  useEffect(() => {
    setClipPreviewAudioOptions({
      sampleId: isBusDriven ? sampleId : null,
      busMuted: isBusDriven && busMuted,
    })
  }, [sampleId, busMuted, isBusDriven])

  useEffect(() => {
    if (!isBusDriven || !sampleId) return
    flushClipPreviewRefresh(localTRef.current, loopSeconds)
  }, [busMuted, loopSeconds, isBusDriven, sampleId])

  useEffect(() => {
    localTRef.current = localT
  }, [localT])

  useEffect(() => {
    playingRef.current = playing
  }, [playing])

  const resetToStart = useCallback(() => {
    setLocalT(0)
    localTRef.current = 0
  }, [])

  const restartPreviewAtStart = useCallback(() => {
    setPlaying(false)
    resetToStart()
    const audio = previewAudioRef.current
    if (audio) {
      audio.pause()
      audio.currentTime = 0
    }
    setWaitingFrame(true)
    flushClipPreviewRefresh(0, loopSeconds)
  }, [resetToStart, loopSeconds])

  const handleSampleChange = useCallback(
    (id: string) => {
      if (id === sampleId) return
      setClipPreviewAudioOptions({
        sampleId: isBusDriven ? id : null,
        busMuted: isBusDriven && busMuted,
      })
      setSampleId(id)
      restartPreviewAtStart()
    },
    [sampleId, isBusDriven, busMuted, restartPreviewAtStart],
  )

  useEffect(() => {
    resetToStart()
    setPlaying(false)
    setLoopOverride(null)
  }, [trackId, clipId, resetToStart])

  useEffect(() => {
    const enabled = apiConnectionStatus === 'connected' && !previewBlocked && !clipDisabled
    clipPreviewClient.setEnabled(enabled)
    if (enabled && clip) {
      flushClipPreviewRefresh(localTRef.current, loopSecondsRef.current)
    } else {
      clearFrame()
      setWaitingFrame(false)
      setPlaying(false)
    }
    return () => clipPreviewClient.setEnabled(false)
  }, [apiConnectionStatus, trackId, clipId, clearFrame, clip, previewBlocked, clipDisabled])

  useEffect(() => clipPreviewClient.onStatus(setStatus), [])

  useEffect(() => {
    return clipPreviewClient.onError((message) => {
      appendEventLog('error', `${t('clip_preview_error')}: ${message}`)
      setWaitingFrame(false)
    })
  }, [appendEventLog, t])

  useEffect(() => {
    return clipPreviewClient.onDrawError(({ message, clip_type }) => {
      const typeLabel = clip_type
      appendEventLog(
        'warn',
        typeLabel
          ? `${t('clip_preview_draw_failed')} (${typeLabel}): ${message}`
          : `${t('clip_preview_draw_failed')}: ${message}`,
      )
    })
  }, [appendEventLog, t])

  useEffect(() => {
    return clipPreviewClient.onFrame(({ width, height, rgba }) => {
      blitFrame(width, height, rgba)
      setWaitingFrame(false)
    })
  }, [blitFrame])

  useEffect(() => {
    if (!clip || apiConnectionStatus !== 'connected' || playing || previewBlocked || clipDisabled) return
    setWaitingFrame(true)
    scheduleClipPreviewRefresh(0, loopSeconds)
  }, [
    apiConnectionStatus,
    playing,
    loopSeconds,
    previewBlocked,
    clipDisabled,
    meta,
    tracks,
    typography,
    colors,
    clipKey,
    clip,
  ])

  useEffect(() => {
    const audio = previewAudioRef.current
    if (!audio || !isBusDriven || silencePreviewAudio || !activeSample) return
    audio.src = activeSample.audio
    audio.loop = false
    if (playing) {
      void audio.play().catch(() => {})
    } else {
      audio.pause()
    }
  }, [activeSample, silencePreviewAudio, playing, isBusDriven])

  useEffect(() => {
    const audio = previewAudioRef.current
    if (!audio || !isBusDriven || silencePreviewAudio) return
    if (!playing) {
      audio.pause()
      audio.currentTime = localT
      return
    }
    const drift = Math.abs(audio.currentTime - localT)
    if (drift > 0.15 || audio.currentTime >= loopSeconds) {
      audio.currentTime = localT % loopSeconds
    }
    if (audio.paused) {
      void audio.play().catch(() => {})
    }
  }, [localT, playing, silencePreviewAudio, isBusDriven, loopSeconds])

  useEffect(() => {
    if (!playing || apiConnectionStatus !== 'connected') return
    const dt = 1 / meta.fps
    const intervalMs = Math.max(16, Math.round(1000 / meta.fps))
    const id = window.setInterval(() => {
      let next = localTRef.current + dt
      if (next >= loopSeconds) {
        next = next % loopSeconds
      }
      localTRef.current = next
      setLocalT(next)
      flushClipPreviewRefresh(next, loopSeconds)
    }, intervalMs)
    return () => window.clearInterval(id)
  }, [playing, loopSeconds, meta.fps, apiConnectionStatus])

  const prevClipKeyRef = useRef(clipKey)
  useEffect(() => {
    if (prevClipKeyRef.current === clipKey) return
    prevClipKeyRef.current = clipKey
    resetToStart()
    if (playingRef.current) {
      flushClipPreviewRefresh(0, loopSeconds)
    }
  }, [clipKey, loopSeconds, resetToStart])

  const handleStop = () => {
    restartPreviewAtStart()
  }

  const handlePlayPause = () => {
    if (playing) {
      setPlaying(false)
      flushClipPreviewRefresh(localTRef.current, loopSeconds)
      return
    }
    setPlaying(true)
  }

  const showOverlay = previewBlocked || !hasFrame || apiConnectionStatus !== 'connected'
  const overlayMessage =
    clipBroken && clip
      ? `${t('prop_plugin_missing')} (${clip.clip_type})`
      : paramsInvalid && clip
        ? formatPreviewInvalidParamsMessage(1)
      : apiConnectionStatus !== 'connected'
      ? t('preview_waiting_api')
      : status === 'connecting'
        ? t('clip_preview_connecting')
        : !hasFrame && waitingFrame
          ? t('preview_loading')
          : !hasFrame
            ? t('clip_preview_placeholder')
            : null

  return (
    <div className="flex flex-row w-full h-full min-h-0">
      <audio ref={previewAudioRef} className="hidden" preload="auto" />
      <PreviewViewport>
        <PreviewCanvasShell
          overlayMessage={showOverlay ? overlayMessage : null}
          pickActive={pickActive}
        >
          <canvas
            ref={canvasRef}
            className={`block h-full w-full [image-rendering:pixelated] ${
              pickActive ? 'cursor-crosshair' : ''
            }`}
            onPointerDown={onCanvasPointerDown}
          />
        </PreviewCanvasShell>
      </PreviewViewport>
      <ClipPreviewControls
        playing={playing}
        localT={localT}
        loopSeconds={loopSeconds}
        showBusAudio={isBusDriven}
        previewSamples={previewSamples}
        sampleId={sampleId}
        busMuted={busMuted}
        onPlayPause={handlePlayPause}
        onStop={handleStop}
        onLoopSeconds={setLoopOverride}
        onSampleId={handleSampleChange}
        onToggleMute={() => setBusMuted((m) => !m)}
      />
    </div>
  )
}

const LOOP_LENGTH_OPTIONS = [8, 15, 45] as const

function CompositionPreviewControls({
  canDownload,
  exporting,
  onDownload,
}: {
  canDownload: boolean
  exporting: boolean
  onDownload: () => void
}) {
  const t = useT()

  return (
    <aside
      className="flex shrink-0 flex-col items-center gap-2 border-l border-border bg-muted/40 py-2"
      style={{ width: COMPOSITION_PREVIEW_CONTROLS_WIDTH_PX }}
      aria-label={t('composition_preview_controls')}
    >
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="h-8 w-8 shrink-0"
        aria-label={t('composition_preview_download')}
        disabled={!canDownload || exporting}
        onClick={onDownload}
      >
        {exporting ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <Download className="h-4 w-4" />
        )}
      </Button>
    </aside>
  )
}

function ClipPreviewControls({
  playing,
  localT,
  loopSeconds,
  showBusAudio,
  previewSamples,
  sampleId,
  busMuted,
  onPlayPause,
  onStop,
  onLoopSeconds,
  onSampleId,
  onToggleMute,
}: {
  playing: boolean
  localT: number
  loopSeconds: number
  showBusAudio: boolean
  previewSamples: PreviewSample[]
  sampleId: string | null
  busMuted: boolean
  onPlayPause: () => void
  onStop: () => void
  onLoopSeconds: (sec: number) => void
  onSampleId: (id: string) => void
  onToggleMute: () => void
}) {
  const t = useT()

  return (
    <aside
      className="flex shrink-0 flex-col items-center gap-2 border-l border-border bg-muted/40 py-2"
      style={{ width: CLIP_PREVIEW_CONTROLS_WIDTH_PX }}
      aria-label={t('clip_preview_controls')}
    >
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="h-8 w-8 shrink-0"
        aria-label={playing ? t('clip_preview_pause') : t('clip_preview_play')}
        onClick={onPlayPause}
      >
        {playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="h-8 w-8 shrink-0"
        aria-label={t('clip_preview_stop')}
        onClick={onStop}
      >
        <Square className="h-3.5 w-3.5" />
      </Button>
      <div
        className="flex flex-col items-center gap-0.5 text-center text-[10px] leading-tight tabular-nums text-foreground"
        title={`${localT.toFixed(1)}s / ${loopSeconds}s`}
      >
        <span>{localT.toFixed(1)}s</span>
        <span className="text-muted-foreground">/</span>
        <span className="text-muted-foreground">{loopSeconds}s</span>
      </div>
      {showBusAudio && previewSamples.length > 0 ? (
        <select
          className="max-w-full rounded border border-border bg-background px-0.5 py-0.5 text-[9px] leading-tight text-foreground"
          aria-label={t('clip_preview_sample')}
          value={sampleId ?? ''}
          onChange={(e) => onSampleId(e.target.value)}
        >
          {previewSamples.map((s) => (
            <option key={s.id} value={s.id}>
              {s.label}
            </option>
          ))}
        </select>
      ) : null}
      {showBusAudio ? (
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-7 w-7 shrink-0"
          aria-label={busMuted ? t('clip_preview_bus_unmute') : t('clip_preview_bus_mute')}
          aria-pressed={busMuted}
          onClick={onToggleMute}
        >
          {busMuted ? <VolumeX className="h-3.5 w-3.5" /> : <Volume2 className="h-3.5 w-3.5" />}
        </Button>
      ) : null}
      <div className="flex flex-col items-center gap-1">
        {LOOP_LENGTH_OPTIONS.map((sec) => (
          <button
            key={sec}
            type="button"
            className={`min-w-[2rem] rounded px-1 py-0.5 text-[10px] tabular-nums transition-colors ${
              loopSeconds === sec
                ? 'bg-primary text-primary-foreground'
                : 'text-muted-foreground hover:bg-muted hover:text-foreground'
            }`}
            aria-pressed={loopSeconds === sec}
            aria-label={`${sec}s`}
            onClick={() => onLoopSeconds(sec)}
          >
            {sec}s
          </button>
        ))}
      </div>
    </aside>
  )
}

/** Centers the preview canvas in the available region (timeline + clip panes). */
function PreviewViewport({ children }: { children: ReactNode }) {
  return (
    <div
      className="flex flex-1 min-h-0 min-w-0 items-center justify-center overflow-hidden bg-black/80 [container-type:size]"
    >
      {children}
    </div>
  )
}

function PreviewCanvasShell({
  overlayMessage,
  pickActive,
  children,
}: {
  overlayMessage: string | null
  pickActive?: boolean
  children: ReactNode
}) {
  const t = useT()
  const { displayAspect } = usePreviewLayout()

  return (
    <div
      className="relative bg-black border border-white/10"
      style={{
        aspectRatio: `${displayAspect}`,
        width: `min(100cqw, calc(100cqh * ${displayAspect}))`,
        height: `min(100cqh, calc(100cqw / ${displayAspect}))`,
      }}
    >
      {children}
      {pickActive ? (
        <div className="pointer-events-none absolute inset-x-0 top-0 z-10 bg-primary/90 px-2 py-1 text-center text-[11px] font-medium text-primary-foreground">
          {t('color_pick_preview_hint')}
        </div>
      ) : null}
      {overlayMessage && !pickActive ? (
        <div className="absolute inset-0 flex items-center justify-center text-white/30 text-sm select-none pointer-events-none px-4 text-center">
          {overlayMessage}
        </div>
      ) : null}
    </div>
  )
}

function PreviewModeToggle({ clipPreviewDisabled }: { clipPreviewDisabled: boolean }) {
  const t = useT()
  const storedMode = useProjectStore((s) => s.appSettings.clipPreviewMode)
  const setAppSettings = useProjectStore((s) => s.setAppSettings)
  const activeMode =
    clipPreviewDisabled && storedMode === 'clip' ? 'composition' : storedMode

  return (
    <div
      className="flex shrink-0 items-center justify-center gap-0.5 border-b border-border bg-muted/30 px-2 py-1"
      role="group"
      aria-label={t('preview_mode_toggle')}
    >
      <button
        type="button"
        disabled={clipPreviewDisabled}
        title={clipPreviewDisabled ? t('preview_clip_disabled_post') : undefined}
        className={`rounded px-2 py-0.5 text-[10px] font-medium transition-colors ${
          activeMode === 'clip'
            ? 'bg-primary text-primary-foreground'
            : 'text-muted-foreground hover:bg-muted hover:text-foreground'
        } disabled:cursor-not-allowed disabled:opacity-40`}
        aria-pressed={activeMode === 'clip'}
        onClick={enterClipPreviewFromToggle}
      >
        {t('preview_clip_label')}
      </button>
      <button
        type="button"
        className={`rounded px-2 py-0.5 text-[10px] font-medium transition-colors ${
          activeMode === 'composition'
            ? 'bg-primary text-primary-foreground'
            : 'text-muted-foreground hover:bg-muted hover:text-foreground'
        }`}
        aria-pressed={activeMode === 'composition'}
        onClick={() => setAppSettings({ clipPreviewMode: 'composition' })}
      >
        {t('preview_composition_label')}
      </button>
    </div>
  )
}

/**
 * Preview pane — one active preview: clip while editing clip params, else composition.
 */
function CompositionPreviewSession({ paused }: { paused: boolean }) {
  useCompositionPreviewSession(paused)
  return null
}

export function PreviewPane() {
  const meta = useProjectStore((s) => s.meta)
  const selection = useProjectStore((s) => s.selection)
  const tracks = useProjectStore((s) => s.tracks)
  const clipPreviewMode = useProjectStore((s) => s.appSettings.clipPreviewMode)
  const layout = usePreviewLayoutState(meta)

  const clipContext = useMemo(() => {
    if (!isClipSelection(selection)) return null
    const track = tracks.find((tr) => tr.id === selection.trackId)
    const clip = track?.clips.find((el) => el.id === selection.clipId)
    if (!track || !clip) return null
    return { track, clip }
  }, [selection, tracks])

  if (!LIVE_PREVIEW_ENABLED && !CLIP_ISOLATED_PREVIEW_ENABLED) {
    return <PreviewPaneDisabled />
  }

  const canUseClipPreview =
    CLIP_ISOLATED_PREVIEW_ENABLED &&
    clipContext != null &&
    clipContext.track.trackType !== 'audio'

  const clipPreviewDisabled = clipContext
    ? !trackSupportsClipPreview(clipContext.track.trackType)
    : false

  const effectiveMode = clipContext
    ? effectiveClipPreviewMode(clipPreviewMode, clipContext.track.trackType)
    : 'composition'

  const showModeToggle = canUseClipPreview
  const compositionSessionPaused =
    LIVE_PREVIEW_ENABLED && canUseClipPreview && effectiveMode === 'clip'

  let body: ReactNode
  if (canUseClipPreview && effectiveMode === 'clip') {
    body = (
      <ClipPreviewLive
        trackId={clipContext.track.id}
        clipId={clipContext.clip.id}
      />
    )
  } else if (!LIVE_PREVIEW_ENABLED) {
    return <PreviewPaneDisabled />
  } else {
    body = <TimelinePreviewLive />
  }

  return (
    <PreviewLayoutContext.Provider value={layout}>
      {LIVE_PREVIEW_ENABLED ? (
        <CompositionPreviewSession paused={compositionSessionPaused} />
      ) : null}
      <div className="flex flex-col w-full h-full min-h-0">
        {showModeToggle ? (
          <PreviewModeToggle clipPreviewDisabled={clipPreviewDisabled} />
        ) : null}
        <ProjectLimitsBanner />
        <div className="flex flex-1 min-h-0 flex-col">{body}</div>
      </div>
    </PreviewLayoutContext.Provider>
  )
}
