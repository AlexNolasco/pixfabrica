import { tKey } from '@/lib/i18n'
import { stopPlaybackOnApiLoss } from '@/lib/playbackOnApiLoss'
import { useProjectStore } from '@/store/projectStore'

let healthProbe: (() => void) | null = null
let probeTimer: ReturnType<typeof setTimeout> | null = null
let lastLogged: 'connected' | 'disconnected' | null = null

const PROBE_DEBOUNCE_MS = 250

export function registerApiHealthProbe(probe: () => void): () => void {
  healthProbe = probe
  return () => {
    if (healthProbe === probe) healthProbe = null
  }
}

function scheduleHealthProbe(): void {
  if (!healthProbe) return
  if (probeTimer) return
  probeTimer = setTimeout(() => {
    probeTimer = null
    healthProbe?.()
  }, PROBE_DEBOUNCE_MS)
}

export function markApiConnected(): void {
  if (lastLogged !== 'connected') {
    useProjectStore.getState().appendEventLog('info', tKey('event_api_connected'))
    lastLogged = 'connected'
  }
}

export function markApiDisconnected(): void {
  if (lastLogged !== 'disconnected') {
    useProjectStore.getState().appendEventLog('error', tKey('event_api_disconnected'))
    lastLogged = 'disconnected'
  }
}

/** Mark API unreachable and run an immediate health probe (debounced). */
export function reportApiUnreachable(): void {
  const state = useProjectStore.getState()
  if (state.apiConnectionStatus === 'connected') {
    stopPlaybackOnApiLoss()
    state.setApiConnectionStatus('disconnected')
    markApiDisconnected()
  }
  scheduleHealthProbe()
}

export function isNetworkFetchError(err: unknown): boolean {
  if (!(err instanceof Error)) return true
  if (err.name === 'AbortError') return true
  // Browser fetch network failures (proxy reset, connection refused, etc.)
  return err instanceof TypeError
}
