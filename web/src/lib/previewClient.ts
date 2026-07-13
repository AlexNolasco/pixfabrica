import { getEffectivePreviewTime } from '@/lib/previewClock'
import { LIVE_PREVIEW_ENABLED, PREVIEW_PLAY_FPS, PREVIEW_STALE_THRESHOLD_SEC } from '@/lib/previewConfig'
import { isOverProjectLimits, previewErrorMessage } from '@/lib/projectLimits'
import { graphHash } from '@/lib/graphHash'
import { toPreviewRenderJob } from '@/lib/previewRenderJob'
import type { RenderJobJson } from '@/lib/renderJob'
import { useAudioAnalysisStore } from '@/store/audioAnalysisStore'
import { applyPrepareWarningsFromPreview } from '@/lib/prepareWarnings'
import { previewDebug } from '@/lib/previewDebug'
import { useProjectStore } from '@/store/projectStore'

export type PreviewConnectionStatus = 'idle' | 'connecting' | 'connected' | 'error'

export interface PreviewFrame {
  width: number
  height: number
  rgba: Uint8ClampedArray
  /** Timeline seconds this frame was rendered for. */
  t: number
}

type FrameListener = (frame: PreviewFrame) => void
type StatusListener = (status: PreviewConnectionStatus) => void
type ErrorListener = (message: string) => void

type PendingPreviewRequest = {
  payload: Record<string, unknown>
  t: number
}

type PendingSnapshotRequest = {
  payload: Record<string, unknown>
  t: number
  resolve: (frame: PreviewFrame) => void
  reject: (reason: Error) => void
}

export function previewWebSocketUrl(): string {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${window.location.host}/ws/preview`
}

function buildGraphFromStore(): { graph: RenderJobJson; t: number; fps: number } {
  const state = useProjectStore.getState()
  const analysisJobs = useAudioAnalysisStore.getState().jobs
  const graph = toPreviewRenderJob(
    {
      meta: state.meta,
      tracks: state.tracks,
      sounds: state.sounds,
      projectSettings: state.projectSettings,
      typography: state.typography,
      colors: state.colors,
      paletteSource: state.paletteSource,
      locale: state.appSettings.locale,
      catalogDetailCache: state.catalogDetailCache,
    },
    analysisJobs,
  )
  return { graph, t: getEffectivePreviewTime(), fps: state.meta.fps }
}

class PreviewClient {
  private ws: WebSocket | null = null
  private inflight = false
  private inflightKind: 'preview' | 'snapshot' = 'preview'
  private pending: PendingPreviewRequest | null = null
  private snapshotQueue: PendingSnapshotRequest[] = []
  private inflightSnapshot: PendingSnapshotRequest | null = null
  private inflightT = 0
  private frameListeners = new Set<FrameListener>()
  private statusListeners = new Set<StatusListener>()
  private errorListeners = new Set<ErrorListener>()
  private status: PreviewConnectionStatus = 'idle'
  private enabled = false
  private closing = false
  private paused = false
  private lastSentHash: string | null = null
  private lastFrame: PreviewFrame | null = null
  private lastFrameHash: string | null = null
  private playPumpActive = false
  private playPumpDesired = false
  private graphRefreshDeferred = false
  private needsServerReprepare = false
  private reprepareInFlight = false
  private inflightReprepare = false
  private lastRequestAt = 0
  private pumpTimer: ReturnType<typeof setTimeout> | null = null

  onFrame(listener: FrameListener): () => void {
    this.frameListeners.add(listener)
    return () => this.frameListeners.delete(listener)
  }

  onStatus(listener: StatusListener): () => void {
    this.statusListeners.add(listener)
    listener(this.status)
    return () => this.statusListeners.delete(listener)
  }

  onError(listener: ErrorListener): () => void {
    this.errorListeners.add(listener)
    return () => this.errorListeners.delete(listener)
  }

  /** Current `t` for the in-flight request (for stale-frame checks). */
  getInflightTime(): number | null {
    return this.inflight ? this.inflightT : null
  }

  setEnabled(on: boolean): void {
    if (!LIVE_PREVIEW_ENABLED) {
      this.disconnect()
      return
    }
    this.enabled = on
    if (on) {
      this.connect()
    } else {
      this.disconnect()
    }
  }

  setPlayPump(on: boolean): void {
    this.playPumpDesired = on
    if (this.paused) return
    this.applyPlayPump(on)
  }

  /** Keep WS + server compositor alive; stop requests, pumps, and canvas delivery. */
  pause(): void {
    if (this.paused) return
    previewDebug('pause')
    this.paused = true
    this.pending = null
    this.reprepareInFlight = false
    this.inflightReprepare = false
    this.applyPlayPump(false)
  }

  /** Graph changed while paused — next resume sends a full graph (no background prepare). */
  markGraphStale(): void {
    previewDebug('markGraphStale')
    this.lastSentHash = null
    this.lastFrameHash = null
  }

  resume(holdPlayPump = false): void {
    if (!this.paused) return
    previewDebug('resume', { warm: this.isWarmForCurrentGraph(), holdPlayPump })
    this.paused = false
    if (this.playPumpDesired && !holdPlayPump && !this.reprepareInFlight) {
      this.applyPlayPump(true)
    }
  }

  isPaused(): boolean {
    return this.paused
  }

  /** Last rendered frame — safe to blit while resuming composition preview. */
  getLastFrame(): PreviewFrame | null {
    if (!this.lastFrame) return null
    const { width, height, rgba, t } = this.lastFrame
    return { width, height, rgba: new Uint8ClampedArray(rgba), t }
  }

  /** True when a cached frame matches the current project graph. */
  isWarmForCurrentGraph(): boolean {
    if (!this.lastFrame || !this.lastFrameHash) return false
    const { graph } = buildGraphFromStore()
    return graphHash(graph) === this.lastFrameHash
  }

  /** Mark graph stale during playback; full prepare runs when the play pump stops. */
  deferGraphRefresh(): void {
    this.graphRefreshDeferred = true
  }

  private applyPlayPump(on: boolean): void {
    this.playPumpActive = on
    if (on) {
      if (!this.inflight) {
        this.requestRefresh()
      }
      return
    }
    if (this.pumpTimer) {
      clearTimeout(this.pumpTimer)
      this.pumpTimer = null
    }
    if (this.graphRefreshDeferred) {
      this.graphRefreshDeferred = false
      this.requestRefresh(true)
    }
  }

  /**
   * One-off frame at project resolution (or preview-only via server cap when fullRes false).
   * Does not update the live preview canvas listeners.
   */
  requestSnapshot(fullRes: boolean): Promise<PreviewFrame> {
    if (!LIVE_PREVIEW_ENABLED || !this.enabled) {
      return Promise.reject(new Error('preview disabled'))
    }
    const state = useProjectStore.getState()
    if (state.apiConnectionStatus !== 'connected') {
      return Promise.reject(new Error('api disconnected'))
    }
    if (isOverProjectLimits(state.tracks, state.sounds, state.serverConfig, state.meta)) {
      return Promise.reject(new Error('project over limits'))
    }

    const { graph, t, fps } = buildGraphFromStore()
    const payload: Record<string, unknown> = { graph, t, fps, fullRes }

    return new Promise((resolve, reject) => {
      this.snapshotQueue.push({
        payload,
        t,
        resolve,
        reject,
      })
      if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
        this.connect()
      } else {
        this.flushQueues()
      }
    })
  }

  /** Force server compositor rebuild even when the graph hash is unchanged. */
  requestReprepare(): void {
    this.markGraphStale()
    this.needsServerReprepare = true
    this.reprepareInFlight = true
    this.applyPlayPump(false)
    if (this.pumpTimer) {
      clearTimeout(this.pumpTimer)
      this.pumpTimer = null
    }
    this.pending = null
    this.requestRefresh(true)
  }

  private finishReprepareIfNeeded(): void {
    if (!this.reprepareInFlight) return
    this.reprepareInFlight = false
    if (this.playPumpDesired && !this.paused) {
      this.applyPlayPump(true)
    }
  }

  /** Request a frame; sends full graph when hash changed or forced. */
  requestRefresh(forceFullGraph = false): void {
    if (!LIVE_PREVIEW_ENABLED || !this.enabled || this.paused) return
    const state = useProjectStore.getState()
    if (state.apiConnectionStatus !== 'connected') return
    if (isOverProjectLimits(state.tracks, state.sounds, state.serverConfig)) return

    const { graph, t, fps } = buildGraphFromStore()
    const hash = graphHash(graph)
    let needsFull = forceFullGraph || this.lastSentHash === null || this.lastSentHash !== hash
    if (needsFull && this.playPumpActive && !this.needsServerReprepare) {
      this.graphRefreshDeferred = true
      needsFull = false
    }

    const payload: Record<string, unknown> = { t, fps }
    if (needsFull) {
      payload.graph = graph
      this.lastSentHash = hash
      if (this.needsServerReprepare) {
        payload.reprepare = true
        this.needsServerReprepare = false
      }
    }

    previewDebug('requestRefresh', {
      forceFullGraph,
      needsFull,
      reprepare: payload.reprepare === true,
      paused: this.paused,
      t,
      playPump: this.playPumpActive,
    })
    this.enqueue({ payload, t })
  }

  /** After a stale skip during play — retry immediately. */
  requestRefreshAfterStale(): void {
    if (this.paused || !this.playPumpActive) return
    this.schedulePlayPump(true)
  }

  /** Call after a frame was displayed (not skipped) to pump the next during play. */
  notifyFrameDisplayed(): void {
    if (this.paused || !this.playPumpActive) return
    this.schedulePlayPump(false)
  }

  private minGapMs(): number {
    return Math.max(16, Math.round(1000 / PREVIEW_PLAY_FPS))
  }

  private schedulePlayPump(immediate: boolean): void {
    if (this.pumpTimer) {
      clearTimeout(this.pumpTimer)
      this.pumpTimer = null
    }
    if (!this.playPumpActive || this.inflight) return

    const elapsed = performance.now() - this.lastRequestAt
    const gap = this.minGapMs()
    const delay = immediate ? 0 : Math.max(0, gap - elapsed)

    this.pumpTimer = setTimeout(() => {
      this.pumpTimer = null
      if (!this.playPumpActive || this.inflight) return
      this.requestRefresh()
    }, delay)
  }

  private setStatus(next: PreviewConnectionStatus): void {
    if (this.status === next) return
    this.status = next
    for (const listener of this.statusListeners) listener(next)
  }

  private emitError(message: string): void {
    for (const listener of this.errorListeners) listener(message)
  }

  private connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN || this.ws?.readyState === WebSocket.CONNECTING) {
      return
    }
    this.lastSentHash = null
    this.lastFrame = null
    this.lastFrameHash = null
    previewDebug('connect')
    this.setStatus('connecting')
    const ws = new WebSocket(previewWebSocketUrl())
    ws.binaryType = 'arraybuffer'
    this.ws = ws

    ws.onopen = () => {
      this.setStatus('connected')
      this.flushQueues()
    }

    ws.onmessage = (event: MessageEvent<ArrayBuffer | string>) => {
      if (typeof event.data === 'string') {
        try {
          const payload = JSON.parse(event.data) as {
            error?: string | Record<string, unknown>
            event?: string
            items?: unknown
          }
          if (payload.event === 'prepare_warnings') {
            applyPrepareWarningsFromPreview(payload.items)
            return
          }
          if (payload.error === 'graph_required') {
            if (this.inflightKind === 'snapshot') {
              this.rejectInflightSnapshot(new Error('graph_required'))
              return
            }
            this.lastSentHash = null
            this.inflight = false
            this.requestRefresh(true)
            return
          }
          if (payload.error) {
            if (this.inflightKind === 'snapshot') {
              this.rejectInflightSnapshot(
                new Error(previewErrorMessage(payload.error, useProjectStore.getState().appSettings.locale)),
              )
            } else {
              this.setStatus('error')
              const locale = useProjectStore.getState().appSettings.locale
              this.emitError(previewErrorMessage(payload.error, locale))
            }
          }
        } catch {
          const message = typeof event.data === 'string' ? event.data : 'Preview error'
          if (this.inflightKind === 'snapshot') {
            this.rejectInflightSnapshot(new Error(message))
          } else {
            this.emitError(message)
          }
        }
        if (this.inflightKind !== 'snapshot') {
          this.inflight = false
          this.onRequestFinished('preview')
        }
        return
      }

      const buffer = event.data
      const frameT = this.inflightT
      const kind = this.inflightKind
      this.inflight = false

      if (!buffer || buffer.byteLength === 0) {
        if (kind === 'snapshot') {
          this.rejectInflightSnapshot(new Error('empty frame'))
        } else {
          this.onRequestFinished('preview')
        }
        return
      }

      const view = new DataView(buffer)
      const width = view.getUint32(0, true)
      const height = view.getUint32(4, true)
      const expected = width * height * 4
      const rgba = new Uint8ClampedArray(buffer, 8, expected)
      const frame: PreviewFrame = {
        width,
        height,
        rgba: new Uint8ClampedArray(rgba),
        t: frameT,
      }

      if (kind === 'snapshot') {
        this.inflightSnapshot?.resolve(frame)
        this.inflightSnapshot = null
        this.onRequestFinished('snapshot')
      } else {
        const wasReprepare = this.inflightReprepare
        this.inflightReprepare = false
        if (this.reprepareInFlight && !wasReprepare) {
          previewDebug('frame discarded (stale before reprepare)')
          this.onRequestFinished('preview')
          return
        }
        this.lastFrame = frame
        this.lastFrameHash = this.lastSentHash
        previewDebug('frame', { t: frameT, w: width, h: height, paused: this.paused, reprepare: wasReprepare })
        if (!this.paused) {
          for (const listener of this.frameListeners) {
            listener(frame)
          }
        }
        if (wasReprepare) {
          this.finishReprepareIfNeeded()
        }
        this.onRequestFinished('preview')
      }
    }

    ws.onerror = () => {
      if (this.closing) return
      this.setStatus('error')
      this.emitError('Preview WebSocket error')
    }

    ws.onclose = () => {
      this.ws = null
      this.inflight = false
      this.lastSentHash = null
      this.lastFrame = null
      this.lastFrameHash = null
      if (this.closing) {
        this.setStatus('idle')
        return
      }
      if (this.enabled) {
        this.setStatus('connecting')
        window.setTimeout(() => {
          if (this.enabled) this.connect()
        }, 1500)
      } else {
        this.setStatus('idle')
      }
    }
  }

  /** After any in-flight request completes (preview or full-res snapshot). */
  private onRequestFinished(kind: 'preview' | 'snapshot'): void {
    if (kind === 'snapshot') {
      this.lastSentHash = null
    }
    this.flushQueues()
    if (this.playPumpActive) {
      this.schedulePlayPump(false)
    } else if (kind === 'snapshot' && !this.inflight && !this.pending) {
      this.requestRefresh(true)
    }
  }

  private rejectInflightSnapshot(err: Error): void {
    this.inflightSnapshot?.reject(err)
    this.inflightSnapshot = null
    this.inflight = false
    this.onRequestFinished('snapshot')
  }

  private rejectAllSnapshots(err: Error): void {
    this.inflightSnapshot?.reject(err)
    this.inflightSnapshot = null
    for (const req of this.snapshotQueue) req.reject(err)
    this.snapshotQueue = []
  }

  private disconnect(): void {
    previewDebug('disconnect')
    this.rejectAllSnapshots(new Error('preview disconnected'))
    this.pending = null
    this.inflight = false
    this.lastSentHash = null
    this.lastFrame = null
    this.lastFrameHash = null
    this.paused = false
    this.playPumpActive = false
    this.playPumpDesired = false
    this.graphRefreshDeferred = false
    if (this.pumpTimer) {
      clearTimeout(this.pumpTimer)
      this.pumpTimer = null
    }
    if (this.ws) {
      this.closing = true
      const ws = this.ws
      ws.onerror = null
      ws.onclose = null
      ws.close()
      this.ws = null
      this.closing = false
    }
    this.setStatus('idle')
  }

  private enqueue(request: PendingPreviewRequest): void {
    this.pending = request
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      this.connect()
      return
    }
    this.flushQueues()
  }

  private flushQueues(): void {
    if (this.inflight || !this.ws || this.ws.readyState !== WebSocket.OPEN) {
      return
    }

    if (this.snapshotQueue.length > 0) {
      const snapshot = this.snapshotQueue.shift()!
      this.inflightSnapshot = snapshot
      this.inflight = true
      this.inflightKind = 'snapshot'
      this.inflightT = snapshot.t
      this.lastRequestAt = performance.now()
      this.ws.send(JSON.stringify(snapshot.payload))
      return
    }

    if (!this.pending) return
    const { payload, t } = this.pending
    this.pending = null
    this.inflight = true
    this.inflightKind = 'preview'
    this.inflightT = t
    this.inflightReprepare = payload.reprepare === true
    this.lastRequestAt = performance.now()
    this.ws.send(JSON.stringify(payload))
  }
}

export const previewClient = new PreviewClient()

export function requestPreviewRefresh(forceFullGraph = false): void {
  previewClient.requestRefresh(forceFullGraph)
}

export function isPreviewFrameStale(frameT: number): boolean {
  return Math.abs(getEffectivePreviewTime() - frameT) > PREVIEW_STALE_THRESHOLD_SEC
}
