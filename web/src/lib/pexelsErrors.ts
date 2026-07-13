const DEFAULT_RATE_LIMIT_COOLDOWN_S = 60

export class PexelsApiError extends Error {
  readonly status: number
  readonly code: string | null
  readonly retryAfterSeconds: number | null

  constructor(
    message: string,
    status: number,
    code: string | null,
    retryAfterSeconds: number | null,
  ) {
    super(message)
    this.name = 'PexelsApiError'
    this.status = status
    this.code = code
    this.retryAfterSeconds = retryAfterSeconds
  }
}

export function isPexelsRateLimited(error: unknown): error is PexelsApiError {
  return error instanceof PexelsApiError && error.status === 429
}

export function pexelsRateLimitCooldownMs(error: PexelsApiError): number {
  const seconds = error.retryAfterSeconds ?? DEFAULT_RATE_LIMIT_COOLDOWN_S
  return Math.max(1, seconds) * 1000
}

function parseDetailObject(raw: unknown): { code: string | null; retryAfterSeconds: number | null } {
  if (typeof raw === 'string') {
    return {
      code: raw.includes('pexels_rate_limited') ? 'pexels_rate_limited' : raw,
      retryAfterSeconds: null,
    }
  }
  if (raw && typeof raw === 'object') {
    const obj = raw as Record<string, unknown>
    const code =
      typeof obj.code === 'string'
        ? obj.code
        : typeof obj.detail === 'string'
          ? obj.detail
          : null
    const retryAfterSeconds =
      typeof obj.retry_after_s === 'number' && Number.isFinite(obj.retry_after_s)
        ? Math.max(1, Math.floor(obj.retry_after_s))
        : null
    return { code, retryAfterSeconds }
  }
  return { code: null, retryAfterSeconds: null }
}

export async function pexelsErrorFromResponse(status: number, res: Response): Promise<PexelsApiError> {
  const body = await res.text().catch(() => '')
  let code: string | null = null
  let retryAfterSeconds: number | null = null

  if (body) {
    try {
      const parsed = JSON.parse(body) as { detail?: unknown }
      const detail = parseDetailObject(parsed.detail ?? parsed)
      code = detail.code
      retryAfterSeconds = detail.retryAfterSeconds
    } catch {
      code = body.includes('pexels_rate_limited') ? 'pexels_rate_limited' : null
    }
  }

  if (status === 429 && retryAfterSeconds == null) {
    retryAfterSeconds = DEFAULT_RATE_LIMIT_COOLDOWN_S
  }

  return new PexelsApiError(
    body ? `Pexels request failed (${status}): ${body}` : `Pexels request failed (${status})`,
    status,
    code,
    retryAfterSeconds,
  )
}
