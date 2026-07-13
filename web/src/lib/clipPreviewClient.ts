import { buildClipPreviewMessage, type ClipPreviewMessage } from '@/lib/clipPreviewPayload'
import { isClipSelection } from '@/lib/selection'
import { CLIP_ISOLATED_PREVIEW_ENABLED } from '@/lib/previewConfig'
import { applyPrepareWarningsFromPreview } from '@/lib/prepareWarnings'
import { useProjectStore } from '@/store/projectStore'

export type ClipPreviewConnectionStatus = 'idle' | 'connecting' | 'connected' | 'error'

export interface ClipPreviewFrame {
  width: number
  height: number
  rgba: Uint8ClampedArray
}

type FrameListener = (frame: ClipPreviewFrame) => void
type StatusListener = (status: ClipPreviewConnectionStatus) => void
type ErrorListener = (message: string) => void
type DrawErrorListener = (payload: { message: string; clip_type?: string }) => void

export function clipPreviewWebSocketUrl(): string {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${window.location.host}/ws/preview/clip`
}

class ClipPreviewClient {
  private ws: WebSocket | null = null
  private inflight = false
  private pending: ClipPreviewMessage | null = null
  private frameListeners = new Set<FrameListener>()
  private statusListeners = new Set<StatusListener>()
  private errorListeners = new Set<ErrorListener>()
  private drawErrorListeners = new Set<DrawErrorListener>()
  private status: ClipPreviewConnectionStatus = 'idle'
  private enabled = false
  private closing = false
  private glPreviewSeen = false
  private idleWaiters: Array<() => void> = []
  /** Bumped on disconnect so stale socket handlers are ignored. */
  private socketGen = 0

  /** True when the last isolated clip preview session used a GL track. */
  hadGlPreview(): boolean {
    return this.glPreviewSeen
  }

  clearGlPreviewFlag(): void {
    this.glPreviewSeen = false
  }

  /** Resolves when the clip preview socket is fully closed and idle. */
  whenIdle(): Promise<void> {
    if (!this.ws && !this.inflight) {
      return Promise.resolve()
    }
    return new Promise((resolve) => {
      const finish = () => {
        this.idleWaiters = this.idleWaiters.filter((w) => w !== finish)
        resolve()
      }
      this.idleWaiters.push(finish)
      if (!this.ws && !this.inflight) {
        finish()
      }
    })
  }

  private resolveIdleWaiters(): void {
    if (this.ws || this.inflight) return
    const waiters = this.idleWaiters
    this.idleWaiters = []
    for (const waiter of waiters) waiter()
  }

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

  onDrawError(listener: DrawErrorListener): () => void {
    this.drawErrorListeners.add(listener)
    return () => this.drawErrorListeners.delete(listener)
  }

  setEnabled(on: boolean): void {
    if (!CLIP_ISOLATED_PREVIEW_ENABLED) {
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

  requestRefresh(message: ClipPreviewMessage): void {
    if (!CLIP_ISOLATED_PREVIEW_ENABLED || !this.enabled) return
    this.enqueue(message)
  }

  private setStatus(next: ClipPreviewConnectionStatus): void {
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
    this.ws = null
    const gen = this.socketGen
    this.closing = false
    this.setStatus('connecting')
    const ws = new WebSocket(clipPreviewWebSocketUrl())
    ws.binaryType = 'arraybuffer'
    this.ws = ws

    ws.onopen = () => {
      if (gen !== this.socketGen || this.ws !== ws) return
      this.setStatus('connected')
      this.flushPending()
    }

    ws.onmessage = (event: MessageEvent<ArrayBuffer | string>) => {
      if (gen !== this.socketGen || this.ws !== ws) return
      if (typeof event.data === 'string') {
        try {
          const payload = JSON.parse(event.data) as {
            error?: string
            event?: string
            message?: string
            clip_type?: string
            items?: unknown
          }
          if (payload.event === 'prepare_warnings') {
            applyPrepareWarningsFromPreview(payload.items)
            return
          }
          if (payload.error) {
            this.setStatus('error')
            this.emitError(payload.error)
          } else if (payload.event === 'draw_error' && payload.message) {
            for (const listener of this.drawErrorListeners) {
              listener({ message: payload.message, clip_type: payload.clip_type })
            }
          }
        } catch {
          this.emitError(event.data)
        }
        this.inflight = false
        this.flushPending()
        return
      }

      const buffer = event.data
      if (!buffer || buffer.byteLength === 0) {
        this.inflight = false
        this.flushPending()
        return
      }

      const view = new DataView(buffer)
      const width = view.getUint32(0, true)
      const height = view.getUint32(4, true)
      const expected = width * height * 4
      const rgba = new Uint8ClampedArray(buffer, 8, expected)
      const frame = {
        width,
        height,
        rgba: new Uint8ClampedArray(rgba),
      }
      for (const listener of this.frameListeners) {
        listener(frame)
      }
      this.inflight = false
      this.flushPending()
    }

    ws.onerror = () => {
      if (gen !== this.socketGen || this.closing) return
      this.setStatus('error')
      this.emitError('Clip preview WebSocket error')
    }

    ws.onclose = () => {
      if (gen !== this.socketGen) return
      this.ws = null
      this.inflight = false
      this.closing = false
      if (this.enabled) {
        this.setStatus('connecting')
        window.setTimeout(() => {
          if (this.enabled && gen === this.socketGen) this.connect()
        }, 1500)
      } else {
        this.setStatus('idle')
        this.resolveIdleWaiters()
      }
    }
  }

  private disconnect(): void {
    this.pending = null
    this.inflight = false
    if (!this.ws) {
      this.setStatus('idle')
      this.resolveIdleWaiters()
      return
    }
    this.socketGen += 1
    this.closing = true
    const ws = this.ws
    this.ws = null
    ws.onerror = null
    const finishClose = () => {
      this.inflight = false
      this.closing = false
      if (!this.enabled) {
        this.setStatus('idle')
      }
      this.resolveIdleWaiters()
    }
    if (ws.readyState === WebSocket.CLOSED) {
      finishClose()
      return
    }
    ws.onclose = () => finishClose()
    ws.close()
  }

  private enqueue(message: ClipPreviewMessage): void {
    if (message.track_kind === 'gl') {
      this.glPreviewSeen = true
    }
    this.pending = message
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      this.connect()
      return
    }
    this.flushPending()
  }

  private flushPending(): void {
    if (this.inflight || !this.pending || !this.ws || this.ws.readyState !== WebSocket.OPEN) {
      return
    }
    const message = this.pending
    this.pending = null
    this.inflight = true
    this.ws.send(JSON.stringify(message))
  }
}

export const clipPreviewClient = new ClipPreviewClient()

export function requestClipPreviewFromStore(t: number, loopSeconds: number): void {
  const state = useProjectStore.getState()
  if (state.apiConnectionStatus !== 'connected') return
  const sel = state.selection
  if (!isClipSelection(sel)) return
  const track = state.tracks.find((tr) => tr.id === sel.trackId)
  const clip = track?.clips.find((el) => el.id === sel.clipId)
  if (!track || !clip) return
  const trackType = track.trackType ?? 'skia'
  if (trackType === 'post' || trackType === 'audio') return

  clipPreviewClient.requestRefresh(
    buildClipPreviewMessage({
      meta: state.meta,
      track,
      clip,
      colors: state.colors,
      typography: state.typography,
      locale: state.appSettings.locale,
      t,
      loopSeconds,
    }),
  )
}
