import { isNetworkFetchError, reportApiUnreachable } from '@/lib/apiConnection'

const BASE = import.meta.env.VITE_API_BASE_URL ?? '/api'
const TOKEN = import.meta.env.VITE_API_TOKEN ?? 'pixfabrica-dev-token'

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers({ Authorization: `Bearer ${TOKEN}` })
  if (init.headers) {
    new Headers(init.headers as HeadersInit).forEach((v, k) => headers.set(k, v))
  }
  try {
    return await fetch(`${BASE}${path}`, { ...init, headers })
  } catch (err) {
    if (isNetworkFetchError(err)) reportApiUnreachable()
    throw err
  }
}

export class ApiHttpError extends Error {
  readonly status: number
  readonly path: string
  readonly method: string
  readonly detail?: string

  constructor(method: string, path: string, status: number, detail?: string) {
    const message = detail
      ? `${method} ${path} → ${status}: ${detail}`
      : `${method} ${path} → ${status}`
    super(message)
    this.name = 'ApiHttpError'
    this.method = method
    this.path = path
    this.status = status
    this.detail = detail
  }
}

async function readApiErrorDetail(res: Response): Promise<string | undefined> {
  const text = await res.text()
  if (!text) return undefined
  try {
    const body = JSON.parse(text) as { detail?: unknown }
    const detail = body.detail
    if (typeof detail === 'string') return detail
    if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
      const record = detail as { code?: string; detail?: string }
      if (record.code === 'gl_unavailable') return JSON.stringify(record)
      if (record.code === 'license_unavailable') return JSON.stringify(record)
      if (typeof record.detail === 'string') return record.detail
      return JSON.stringify(detail)
    }
    if (Array.isArray(detail)) {
      return detail
        .map((item) => {
          if (typeof item === 'string') return item
          if (item && typeof item === 'object' && 'msg' in item) {
            const loc = 'loc' in item && Array.isArray(item.loc) ? item.loc.join('.') : ''
            return loc ? `${loc}: ${String(item.msg)}` : String(item.msg)
          }
          return JSON.stringify(item)
        })
        .join('; ')
    }
  } catch {
    return text.length > 200 ? `${text.slice(0, 200)}…` : text
  }
  return text.length > 200 ? `${text.slice(0, 200)}…` : text
}

async function throwApiHttpError(method: string, path: string, res: Response): Promise<never> {
  const detail = await readApiErrorDetail(res)
  throw new ApiHttpError(method, path, res.status, detail)
}

export async function apiGet<T>(path: string): Promise<T> {
  const res = await apiFetch(path)
  if (!res.ok) await throwApiHttpError('GET', path, res)
  return res.json() as Promise<T>
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const res = await apiFetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) await throwApiHttpError('POST', path, res)
  return res.json() as Promise<T>
}

export async function apiPatch<T>(path: string, body?: unknown): Promise<T> {
  const res = await apiFetch(path, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) await throwApiHttpError('PATCH', path, res)
  return res.json() as Promise<T>
}

export async function apiDelete<T>(path: string): Promise<T> {
  const res = await apiFetch(path, { method: 'DELETE' })
  if (!res.ok) await throwApiHttpError('DELETE', path, res)
  return res.json() as Promise<T>
}
