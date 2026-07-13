import { apiDelete, apiFetch, apiGet, apiPost } from '@/lib/apiClient'

export type JobStatus =
  | 'queued'
  | 'preparing'
  | 'rendering'
  | 'done'
  | 'cancelled'
  | 'failed'
  | 'interrupted'

export interface JobRecord {
  id: string
  status: JobStatus
  created_at: string
  started_at: string | null
  finished_at: string | null
  render_duration_ms: number | null
  render_parallelism_requested: 'single' | 'multi' | null
  render_parallelism_effective: 'single' | 'multi' | null
  title: string
  width: number
  height: number
  fps: number
  duration_s: number
  error: string | null
  submitted_by: string | null
  executor: string
  frame: number
  total: number
  percent: number
}

const ACTIVE_STATUSES: ReadonlySet<JobStatus> = new Set([
  'queued',
  'preparing',
  'rendering',
])

const TERMINAL_STATUSES: ReadonlySet<JobStatus> = new Set([
  'done',
  'cancelled',
  'failed',
  'interrupted',
])

export function isJobActive(status: JobStatus): boolean {
  return ACTIVE_STATUSES.has(status)
}

export function isJobTerminal(status: JobStatus): boolean {
  return TERMINAL_STATUSES.has(status)
}

export function listJobs(): Promise<JobRecord[]> {
  return apiGet<JobRecord[]>('/jobs')
}

export function getJob(jobId: string): Promise<JobRecord> {
  return apiGet<JobRecord>(`/jobs/${jobId}`)
}

/** List rows are disk metadata only; active jobs need GET /jobs/{id} for live progress. */
export async function hydrateActiveJobs(rows: JobRecord[]): Promise<JobRecord[]> {
  return Promise.all(
    rows.map(async (row) => {
      if (!isJobActive(row.status)) return row
      try {
        return await getJob(row.id)
      } catch {
        return row
      }
    }),
  )
}

/** Prefer the row with more complete live progress (WS may be ahead of a poll). */
export function mergeJobProgress(a: JobRecord, b: JobRecord): JobRecord {
  if (a.id !== b.id) return b
  const total = Math.max(a.total, b.total)
  const percent = Math.max(a.percent, b.percent)
  const frame = Math.max(a.frame, b.frame)
  return { ...b, total, percent, frame }
}

export function createJob(graph: Record<string, unknown>): Promise<{ job_id: string }> {
  return apiPost<{ job_id: string }>('/jobs', { graph })
}

export function cancelJob(jobId: string): Promise<{ status: string }> {
  return apiDelete<{ status: string }>(`/jobs/${jobId}`)
}

export function removeJobArtifacts(jobId: string): Promise<{ status: string }> {
  return apiDelete<{ status: string }>(`/jobs/${jobId}/artifacts`)
}

export async function fetchJobVideoBlob(
  jobId: string,
  disposition: 'inline' | 'attachment' = 'inline',
): Promise<Blob> {
  const res = await apiFetch(`/jobs/${jobId}/video?disposition=${disposition}`)
  if (!res.ok) {
    throw new Error(`video fetch failed (${res.status})`)
  }
  return res.blob()
}

export type DiscordExportMaxMb = 8 | 50

export async function fetchJobDiscordVideoBlob(
  jobId: string,
  maxMb: DiscordExportMaxMb = 8,
): Promise<Blob> {
  const res = await apiFetch(`/jobs/${jobId}/video/discord?max_mb=${maxMb}`)
  if (!res.ok) {
    let message = `Discord export failed (${res.status})`
    try {
      const body = (await res.json()) as { detail?: string }
      if (typeof body.detail === 'string' && body.detail.length > 0) {
        message = body.detail
      }
    } catch {
      // ignore non-JSON error bodies
    }
    throw new Error(message)
  }
  return res.blob()
}

export function jobProgressWebSocketUrl(jobId: string): string {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${window.location.host}/ws/jobs/${jobId}/progress`
}
