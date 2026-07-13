/** Compose readiness from GET /health (matches API ComposeHealthResponse). */

export interface ComposeHealth {
  model: string
  modelAvailable: boolean
  toolsCapable: boolean | null
  ready: boolean
  reason: string | null
}

export interface HealthPayload {
  ffmpeg?: boolean
  gl?: {
    available?: boolean
    reason?: string | null
    renderer?: string | null
  }
  ollama?: boolean
  pexels_available?: boolean
  compose?: {
    model: string
    model_available: boolean
    tools_capable: boolean | null
    ready: boolean
    reason: string | null
  }
}

export function parseComposeHealth(payload: HealthPayload): ComposeHealth | null {
  const raw = payload.compose
  if (!raw || typeof raw.model !== 'string') return null
  return {
    model: raw.model,
    modelAvailable: Boolean(raw.model_available),
    toolsCapable:
      typeof raw.tools_capable === 'boolean' ? raw.tools_capable : null,
    ready: Boolean(raw.ready),
    reason: typeof raw.reason === 'string' ? raw.reason : null,
  }
}
